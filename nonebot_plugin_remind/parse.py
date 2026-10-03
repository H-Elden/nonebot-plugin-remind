"""中文自然语言时间解析模块。

使用 jionlp 离线解析中文时间表达式，大模型（OpenAI 兼容接口）作为可选兜底。
"""

from __future__ import annotations

import ast
import json
import os
import sys
import time as _time
from datetime import datetime, timedelta

# jionlp 在 import 时会 print 推广信息，屏蔽 stdout
_devnull = open(os.devnull, "w")
_stdout = sys.stdout
sys.stdout = _devnull
try:
    import jionlp as jio
finally:
    sys.stdout = _stdout
    _devnull.close()

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from nonebot.log import logger

from .llm import parsed_time_llm

_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


# ── 公开接口 ────────────────────────────────────────────────


async def parse_time(text: str) -> datetime | CronTrigger | IntervalTrigger | None:
    """解析中文时间表达式。

    Returns:
        datetime        — 单次提醒
        CronTrigger     — 循环提醒（带锚点，如「每天8:00」）
        IntervalTrigger — 间隔循环（如「每2小时」）
        None            — 无法解析
    """
    if not text or not text.strip():
        return None

    # 1. jionlp 离线解析
    result = _parse_with_jionlp(text)
    if result is not None:
        return result

    # 2. 大模型兜底（未配置或 SDK 未安装时内部静默跳过）
    return await _parse_time_with_llm(text)


async def extract_time_and_message(
    text: str,
) -> tuple[datetime | CronTrigger | IntervalTrigger | None, str]:
    """从混合文本中提取时间和剩余消息。

    利用 jio.ner.extract_time 精确定位时间子串的位置，
    将其从原文中移除后得到剩余消息。

    示例:
        "明天打胶"   → (datetime(明天), "打胶")
        "一分钟后开会" → (datetime(一分钟后), "开会")
        "下午3点交作业" → (datetime(下午3点), "交作业")

    Returns:
        (parsed_time, remaining_message)
        若无法识别时间，返回 (None, 原始text)
    """
    if not text or not text.strip():
        return None, text

    # 使用 jio.ner.extract_time 获取带位置信息的时间实体
    try:
        entities = jio.ner.extract_time(text, time_base=_time.time())
    except Exception as e:
        logger.debug(f"jionlp extract_time 异常: {e}")
        return None, text

    if not entities:
        # jionlp 提取不到，尝试大模型兜底（此时无法分离消息）
        parsed = await parse_time(text)
        return parsed, "" if parsed else text

    # 取第一个时间实体
    entity = entities[0]
    time_text = entity["text"]
    offset = entity["offset"]  # [start, end]

    # 解析时间
    parsed = await parse_time(time_text)
    if parsed is None:
        return None, text

    # 从原文中移除时间部分，得到剩余消息
    remaining = (text[: offset[0]] + text[offset[1] :]).strip()
    return parsed, remaining


# ── jionlp 解析 ─────────────────────────────────────────────


def _parse_with_jionlp(text: str) -> datetime | CronTrigger | IntervalTrigger | None:
    """使用 jionlp 解析时间表达式。"""
    try:
        result = jio.parse_time(text, time_base=_time.time())
    except Exception as e:
        logger.debug(f"jionlp 解析异常: {e}")
        return None

    if result is None:
        return None

    time_type = result.get("type")
    time_data = result.get("time")
    logger.debug(f"jionlp 原始结果: type={time_type}, time={time_data}")

    if not isinstance(time_type, str):
        return None

    converter = {
        "time_point": _parse_timestamp,
        "time_span": _parse_timestamp,
        "time_delta": _delta_to_datetime,
        "time_period": _period_to_trigger,
    }.get(time_type)

    if converter is None:
        logger.warning(f"不支持的 jionlp 时间类型: {time_type}")
        return None

    parsed = converter(time_data)
    if parsed is not None:
        logger.info(f'jionlp 解析: "{text}" → {parsed}')
    return parsed


# ── 类型转换 ─────────────────────────────────────────────────


def _parse_timestamp(data: list) -> datetime | None:
    """time_point / time_span → datetime（取起始时间）。

    data 格式: ['2026-03-15 15:00:00', '2026-03-15 15:00:00']
    """
    try:
        return datetime.strptime(data[0], _DATETIME_FMT)
    except (IndexError, ValueError, TypeError):
        return None


def _delta_to_datetime(data) -> datetime | None:
    """time_delta → now + timedelta。

    data 格式: {'hour': 0.5} 或 [{'hour': 0.5}, {'hour': 1.0}]（模糊范围取首值）
    """
    try:
        if isinstance(data, list):
            data = data[0] if data else {}

        mapping = {
            "day": "days",
            "hour": "hours",
            "minute": "minutes",
            "second": "seconds",
        }
        kwargs: dict[str, float] = {}
        for src, dst in mapping.items():
            if src in data:
                kwargs[dst] = float(data[src])

        # month / year 不被 timedelta 直接支持，用近似天数
        if "month" in data:
            kwargs["days"] = kwargs.get("days", 0) + float(data["month"]) * 30
        if "year" in data:
            kwargs["days"] = kwargs.get("days", 0) + float(data["year"]) * 365

        return datetime.now() + timedelta(**kwargs) if kwargs else None
    except (TypeError, ValueError):
        return None


def _period_to_trigger(data: dict) -> CronTrigger | IntervalTrigger | None:
    """time_period → CronTrigger 或 IntervalTrigger。

    data 格式: {'delta': {'day': 1}, 'point': {'time': [...], 'string': '...'}}
    - point 为空（纯间隔，如「每2小时」）→ IntervalTrigger；
    - point 有值（带锚点，如「每天8:00」）→ CronTrigger。
    """
    try:
        delta = data.get("delta", {})
        point = data.get("point")

        if not delta:
            return None

        if point is None:
            return _build_interval_trigger(delta)

        pt = _extract_point_time(point)
        if pt is None:
            return None

        params = _build_cron_params(delta, pt)
        return CronTrigger(**params) if params else None
    except (TypeError, ValueError) as e:
        logger.debug(f"time_period → 触发器失败: {e}")
        return None


def _build_interval_trigger(delta: dict) -> IntervalTrigger | None:
    """根据无锚点的 delta 构建 IntervalTrigger（每 N 秒/分钟/小时/天/周）。

    月、年长度不固定，无法用固定间隔精确表达，维持不支持。
    """
    if "second" in delta:
        total_seconds = float(delta["second"])
    elif "minute" in delta:
        total_seconds = float(delta["minute"]) * 60
    elif "hour" in delta:
        total_seconds = float(delta["hour"]) * 3600
    elif "day" in delta:
        total_seconds = float(delta["day"]) * 86400
    elif "month" in delta or "year" in delta:
        logger.warning("暂不支持「每 N 个月 / 每 N 年」的间隔提醒")
        return None
    else:
        return None

    if total_seconds < 1:
        return None
    return IntervalTrigger(seconds=int(total_seconds))


def _extract_point_time(point: dict | None) -> datetime | None:
    """从 time_period.point 中提取 datetime。"""
    if not point or "time" not in point:
        return None
    try:
        return datetime.strptime(point["time"][0], _DATETIME_FMT)
    except (IndexError, ValueError):
        return None


def _build_cron_params(delta: dict, pt: datetime) -> dict:
    """根据 delta 类型和 point 时间构建 CronTrigger 参数。"""
    if "hour" in delta:
        # 每小时的 XX 分
        hour_val = float(delta["hour"])
        if hour_val != 1:
            logger.warning(f"不支持每 {delta['hour']} 小时的 Cron 周期")
            return {}
        return {"minute": pt.minute}

    if "day" in delta:
        day_val = int(delta["day"])
        if day_val == 1:
            # 每天
            return {"hour": pt.hour, "minute": pt.minute}
        if day_val == 7:
            # 每周（weekday: 0=Mon … 6=Sun，与 APScheduler 一致）
            return {
                "day_of_week": pt.weekday(),
                "hour": pt.hour,
                "minute": pt.minute,
            }
        logger.warning(f"不支持每 {day_val} 天的 Cron 周期")
        return {}

    if "month" in delta:
        month_val = int(delta["month"])
        if month_val != 1:
            logger.warning(f"不支持每 {month_val} 个月的 Cron 周期")
            return {}
        # 每月
        return {"day": pt.day, "hour": pt.hour, "minute": pt.minute}

    if "year" in delta:
        year_val = int(delta["year"])
        if year_val != 1:
            logger.warning(f"不支持每 {year_val} 年的 Cron 周期")
            return {}
        # 每年
        return {
            "month": pt.month,
            "day": pt.day,
            "hour": pt.hour,
            "minute": pt.minute,
        }

    return {}


# ── 大模型兜底 ──────────────────────────────────────────────


# interval 回复允许的时间单位（周按 7 天折算；月、年长度不固定，维持不支持）
_INTERVAL_UNITS = ("second", "minute", "hour", "day", "week")


def _extract_json_payload(reply: str) -> dict | None:
    """从模型回复中提取 JSON 对象（容忍代码块围栏与多余文字）。"""
    start = reply.find("{")
    end = reply.rfind("}")
    if start == -1 or end <= start:
        return None
    payload_text = reply[start : end + 1]
    try:
        payload = json.loads(payload_text)
    except ValueError:
        try:
            # 容忍模型按旧习惯回复 python 字典字面量（单引号）的情况
            payload = ast.literal_eval(payload_text)
        except (ValueError, SyntaxError) as e:
            logger.warning(f'大模型回复无法解析: "{reply}"（{e}）')
            return None
    if not isinstance(payload, dict):
        return None
    return payload


async def _parse_time_with_llm(
    text: str,
) -> datetime | CronTrigger | IntervalTrigger | None:
    """大模型统一兜底：按回复中的 type 构建对应触发器。"""
    logger.info(f'大模型兜底解析: "{text}"')
    reply = await parsed_time_llm(text)
    if not reply:
        return None

    payload = _extract_json_payload(reply)
    if payload is None:
        return None

    kind = payload.get("type")
    if kind == "date":
        value = payload.get("datetime")
        if not isinstance(value, str):
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            logger.warning(f'大模型返回的时间格式不正确: "{value}"')
            return None
    if kind == "cron":
        params = payload.get("params")
        if not isinstance(params, dict):
            return None
        try:
            return CronTrigger(**params)
        except (TypeError, ValueError) as e:
            logger.warning(f"按大模型参数创建 CronTrigger 失败: {e}")
            return None
    if kind == "interval":
        return _interval_from_llm(payload)
    logger.warning(f'大模型回复了未知的触发器类型: "{kind}"')
    return None


def _interval_from_llm(payload: dict) -> IntervalTrigger | None:
    """按 interval 回复中的 value+unit 构建 IntervalTrigger。"""
    unit = payload.get("unit")
    if unit not in _INTERVAL_UNITS:
        logger.warning(f"不支持的间隔单位: {unit!r}")
        return None
    value = payload.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    delta = {"day": float(value) * 7} if unit == "week" else {unit: float(value)}
    return _build_interval_trigger(delta)
