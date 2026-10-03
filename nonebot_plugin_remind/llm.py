# pyright: reportMissingImports=false
"""大模型兜底解析客户端（OpenAI 兼容接口）。

- 延迟导入 openai SDK：仅在实际发起解析时导入；SDK 未安装或未配置
  API Key 时静默降级为不可用，不影响插件本体加载与 jionlp 离线主链路；
- 一次调用由模型自判触发器类型（单次 / 固定时点循环 / 间隔循环），
  统一回复 JSON 参数；
- 可对接任意兼容 OpenAI Chat Completions 协议的服务
  （智谱、DeepSeek、硅基流动、本地 vLLM 等）。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from nonebot.log import logger

from .config import plugin_config

if TYPE_CHECKING:
    from openai import AsyncOpenAI

# 单次请求超时（秒）
_TIMEOUT_SECONDS = 30.0


def _time_system_prompt() -> str:
    """构建统一解析提示词（含当前时间基准与三类触发器输出约定）。"""
    return (
        f"当前时间是{datetime.now().strftime('%Y-%m-%d %H:%M')}（24小时制时间），"
        "我提供一个关于时间的文本表述，请你以当前时间为基准判断它的类型，"
        "仅回复一行 JSON（不要用 markdown 代码块包裹，不要输出其他任何内容）：\n"
        '1. 单个时间点：回复 {"type": "date", "datetime": "YYYY-MM-DD HH:MM"}，'
        "采用24小时制（提示：晚上12点或者24点都应回复为第二天的0点；"
        "如果表述中不能明确是上午或是下午则默认按上午来回复；"
        '如果这样的时间点早于当前时刻则回复 "None"）；\n'
        '2. 固定时点的循环（如"每天8点"、"每周三14:00"、"每月15号"）：'
        '回复 {"type": "cron", "params": {...}}，'
        "params 为 python CronTrigger() 的参数字典"
        "（可用字段：month、day、day_of_week（数字 0 表示周一）、hour、minute、"
        'second），例如 {"hour": 8, "minute": 0}；\n'
        '3. 从当前时刻起算的间隔循环（如"每隔30分钟"、"每2小时"、"每两周"）：'
        '回复 {"type": "interval", "value": N, "unit": "..."}，'
        "unit 只能为 second、minute、hour、day、week 之一"
        '（例如 {"value": 30, "unit": "minute"}）；\n'
        "如果无法确定类型，或者不支持该表述"
        '（例如"每N个月"、"每N年"的间隔），回复 "None"。'
    )


def _get_client() -> AsyncOpenAI | None:
    """按需创建 OpenAI 兼容客户端；未配置或 SDK 缺失时返回 None。"""
    if not plugin_config.remind_llm_api_key:
        logger.debug("未配置大模型 API Key，跳过兜底解析")
        return None

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning(
            "未安装 openai SDK，大模型兜底不可用"
            "（安装方式：pip install nonebot-plugin-remind[llm]）"
        )
        return None

    try:
        return AsyncOpenAI(
            api_key=plugin_config.remind_llm_api_key,
            base_url=plugin_config.remind_llm_base_url or None,
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.error(f"初始化大模型客户端失败: {e}")
        return None


async def _chat(
    model: str,
    messages: list[dict],
    *,
    temperature: float,
    max_tokens: int,
) -> str | None:
    """调用兼容接口完成一次对话，返回文本内容；失败时返回 None。"""
    client = _get_client()
    if client is None:
        return None

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error(f"大模型请求失败: {e}")
        return None

    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        return None
    return content.strip()


async def parsed_time_llm(time_text: str) -> str | None:
    """用大模型解析时间表述，由模型自判触发器类型并返回统一 JSON 回复。

    Returns:
        单行 JSON 文本（type 为 date / cron / interval），
        或 "None"（无法解析）、None（未配置 / 请求失败）。
    """
    if not time_text:
        return None
    if not plugin_config.remind_llm_model:
        logger.debug("未配置大模型（remind_llm_model），跳过兜底解析")
        return None
    return await _chat(
        plugin_config.remind_llm_model,
        [
            {"role": "system", "content": _time_system_prompt()},
            {"role": "user", "content": time_text},
        ],
        temperature=0.3,
        max_tokens=100,
    )
