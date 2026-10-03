"""大模型兜底解析客户端（OpenAI 兼容接口）。

- 延迟导入 openai SDK：仅在实际发起解析时导入；SDK 未安装或未配置
  API Key 时静默降级为不可用，不影响插件本体加载与 jionlp 离线主链路；
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

# 循环提醒解析的系统提示词（要求模型仅返回 CronTrigger 参数字典）
_CRON_SYSTEM_PROMPT = (
    "我提供一个时间的文本表述用于创建python中的CronTrigger()实例来实现定时，"
    "请你仅回复一个参数字典（不要用makedown的代码块包裹），用于向CronTrigger()中传递参数。"
)


def _datetime_system_prompt() -> str:
    """构建单次提醒解析的系统提示词（含当前时间基准）。"""
    return (
        f'当前时间是{datetime.now().strftime("%Y-%m-%d %H:%M")}（24小时制时间），'
        "我提供一个关于时间的表述，请你以当前时间为基准，仅回复我一个未来最符合该表述的时间，"
        '采用"YYYY-MM-DD HH:MM"的格式回复24小时制时间'
        "（提示：晚上12点或者24点都应回复为第二天的0点）；"
        "如果表述中不能明确是上午或是下午则默认按上午来回复。"
        '特殊情况：如果符合的时间早于当前 或者 如果我提供的表述无法表示正确的时间则回复"None"。'
    )


def _get_client() -> AsyncOpenAI | None:
    """按需创建 OpenAI 兼容客户端；未配置或 SDK 缺失时返回 None。"""
    if not plugin_config.llm_api_key:
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
            api_key=plugin_config.llm_api_key,
            base_url=plugin_config.llm_base_url or None,
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


async def parsed_datetime_llm(time_text: str) -> str | None:
    """用大模型解析单次提醒时间。

    Returns:
        "YYYY-MM-DD HH:MM" 文本，或 None（未配置 / 请求失败）。
    """
    if not time_text:
        return None
    if not plugin_config.llm_model:
        logger.debug("未配置单次提醒模型（llm_model），跳过兜底解析")
        return None
    return await _chat(
        plugin_config.llm_model,
        [
            {"role": "system", "content": _datetime_system_prompt()},
            {"role": "user", "content": time_text},
        ],
        temperature=0.25,
        max_tokens=20,
    )


async def parsed_cron_time_llm(time_text: str) -> str | None:
    """用大模型解析循环提醒的 CronTrigger 参数字典。

    Returns:
        参数字典文本（如 "{'hour': 8, 'minute': 0}"），或 None（未配置 / 请求失败）。
    """
    if not time_text:
        return None
    if not plugin_config.llm_model_cron:
        logger.debug("未配置循环提醒模型（llm_model_cron），跳过兜底解析")
        return None
    return await _chat(
        plugin_config.llm_model_cron,
        [
            {"role": "system", "content": _CRON_SYSTEM_PROMPT},
            {"role": "user", "content": time_text},
        ],
        temperature=0.75,
        max_tokens=40,
    )
