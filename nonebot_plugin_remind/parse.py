"""中文自然语言时间解析模块。

使用 jionlp 离线解析中文时间表达式，GLM-4 作为可选兜底。
"""

from __future__ import annotations

import ast
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
from nonebot.log import logger

from .glm4 import parsed_cron_time_glm4, parsed_datetime_glm4

_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


# ── 公开接口 ────────────────────────────────────────────────


async def parse_time(text: str) -> datetime | CronTrigger | None:
    """解析中文时间表达式。

    Returns:
        datetime    — 单次提醒
        CronTrigger — 循环提醒
        None        — 无法解析
    """
    if not text or not text.strip():
        return None

    # 1. jionlp 离线解析
    result = _parse_with_jionlp(text)
    if result is not None:
        return result

    # 2. GLM-4 兜底
    try:
        if text.startswith("每"):
            return await _parse_cron_with_glm4(text)
        return await _parse_date_with_glm4(text)
    except Exception as e:
        logger.error(f"GLM-4 解析异常: {e}")
        return None


async def extract_time_and_message(
    text: str,
) -> tuple[datetime | CronTrigger | None, str]:
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
        # jionlp 提取不到，尝试 GLM-4 兜底（此时无法分离消息）
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


def _parse_with_jionlp(text: str) -> datetime | CronTrigger | None:
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
        "time_period": _period_to_cron,
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


def _period_to_cron(data: dict) -> CronTrigger | None:
    """time_period → CronTrigger。

    data 格式: {'delta': {'day': 1}, 'point': {'time': [...], 'string': '...'}}
    """
    try:
        delta = data.get("delta", {})
        point = data.get("point")

        if not delta:
            return None

        pt = _extract_point_time(point)
        if pt is None:
            return None

        params = _build_cron_params(delta, pt)
        return CronTrigger(**params) if params else None
    except (TypeError, ValueError) as e:
        logger.debug(f"time_period → CronTrigger 失败: {e}")
        return None


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
        # 每月
        return {"day": pt.day, "hour": pt.hour, "minute": pt.minute}

    if "year" in delta:
        # 每年
        return {
            "month": pt.month,
            "day": pt.day,
            "hour": pt.hour,
            "minute": pt.minute,
        }

    return {}


# ── GLM-4 兜底 ──────────────────────────────────────────────


async def _parse_date_with_glm4(text: str) -> datetime | None:
    """GLM-4 解析单次提醒时间。"""
    logger.info(f'GLM-4 解析单次提醒: "{text}"')
    res = await parsed_datetime_glm4(text)
    if isinstance(res, str) and res not in ("None", "Error", "Failed", "Timeout"):
        try:
            return datetime.strptime(res, "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return None


async def _parse_cron_with_glm4(text: str) -> CronTrigger | None:
    """GLM-4 解析循环提醒时间。"""
    logger.info(f'GLM-4 解析循环提醒: "{text}"')
    params_str = await parsed_cron_time_glm4(text)
    try:
        params = ast.literal_eval(params_str)
        if isinstance(params, dict):
            return CronTrigger(**params)
    except (ValueError, SyntaxError):
        pass
    return None
