"""大模型兜底链路单元测试：mock OpenAI 兼容接口，不发起真实请求。"""

import sys
from datetime import datetime, timedelta
from types import ModuleType, SimpleNamespace

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from nonebot_plugin_remind.config import plugin_config
from nonebot_plugin_remind.llm import parsed_time_llm
from nonebot_plugin_remind.parse import _parse_time_with_llm


@pytest.fixture
def configured(monkeypatch):
    """临时配置大模型参数（默认未配置）。"""
    monkeypatch.setattr(plugin_config, "remind_llm_api_key", "test-key")
    monkeypatch.setattr(plugin_config, "remind_llm_base_url", "")
    monkeypatch.setattr(plugin_config, "remind_llm_model", "test-model")


def _install_fake_openai(monkeypatch, *, content=None, error=None, client_error=None):
    """向 sys.modules 注入假 openai 模块，并记录调用参数。"""
    calls = {}

    class _FakeCompletions:
        async def create(self, **kwargs):
            calls["create_kwargs"] = kwargs
            if error is not None:
                raise error
            message = SimpleNamespace(content=content)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            if client_error is not None:
                raise client_error
            calls["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    fake_module = ModuleType("openai")
    setattr(fake_module, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return calls


async def test_unconfigured_skips_silently(monkeypatch, caplog):
    """未配置 API Key 时静默跳过，不产生 warning 日志。"""
    monkeypatch.setattr(plugin_config, "remind_llm_api_key", "")
    with caplog.at_level("WARNING"):
        assert await parsed_time_llm("明天下午3点") is None
    assert not caplog.records


async def test_empty_text_returns_none(configured, monkeypatch):
    _install_fake_openai(monkeypatch, content="None")
    assert await parsed_time_llm("") is None


async def test_unconfigured_model_skips(configured, monkeypatch):
    """未配置模型名称时同样静默跳过。"""
    monkeypatch.setattr(plugin_config, "remind_llm_model", "")
    _install_fake_openai(monkeypatch, content="None")
    assert await parsed_time_llm("明天") is None


async def test_single_request_carries_model_and_key(configured, monkeypatch):
    """配置齐全时发起一次调用，携带模型名与 API Key。"""
    reply = '{"type": "date", "datetime": "2026-10-04 09:00"}'
    calls = _install_fake_openai(monkeypatch, content=reply)
    assert await parsed_time_llm("国庆假期早上9点") == reply
    assert calls["create_kwargs"]["model"] == "test-model"
    assert calls["client_kwargs"]["api_key"] == "test-key"


async def test_date_success(configured, monkeypatch):
    """date 类型回复被解析为 datetime。"""
    _install_fake_openai(
        monkeypatch, content='{"type": "date", "datetime": "2026-10-04 09:00"}'
    )
    assert await _parse_time_with_llm("某表述") == datetime(2026, 10, 4, 9, 0)


async def test_cron_success(configured, monkeypatch):
    """cron 类型回复被构建为 CronTrigger。"""
    _install_fake_openai(
        monkeypatch, content='{"type": "cron", "params": {"hour": 8, "minute": 30}}'
    )
    trigger = await _parse_time_with_llm("每天早上8点半")
    assert isinstance(trigger, CronTrigger)
    fields = {field.name: str(field) for field in trigger.fields}
    assert fields["hour"] == "8"
    assert fields["minute"] == "30"


async def test_interval_success(configured, monkeypatch):
    """interval 类型回复被构建为 IntervalTrigger。"""
    _install_fake_openai(
        monkeypatch, content='{"type": "interval", "value": 30, "unit": "minute"}'
    )
    trigger = await _parse_time_with_llm("每隔半小时")
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval == timedelta(minutes=30)


async def test_interval_week_unit(configured, monkeypatch):
    """week 单位按 7 天折算。"""
    _install_fake_openai(
        monkeypatch, content='{"type": "interval", "value": 2, "unit": "week"}'
    )
    trigger = await _parse_time_with_llm("每两周")
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval == timedelta(days=14)


async def test_interval_month_unsupported(configured, monkeypatch):
    """月、年间隔维持不支持。"""
    _install_fake_openai(
        monkeypatch, content='{"type": "interval", "value": 1, "unit": "month"}'
    )
    assert await _parse_time_with_llm("每个月") is None


async def test_reply_none(configured, monkeypatch):
    """模型回复 "None" 表示无法解析。"""
    _install_fake_openai(monkeypatch, content="None")
    assert await _parse_time_with_llm("无法解析的表述") is None


async def test_code_fence_reply_tolerated(configured, monkeypatch):
    """回复被 markdown 代码块包裹时仍可解析。"""
    _install_fake_openai(
        monkeypatch,
        content='```json\n{"type": "date", "datetime": "2026-10-04 09:00"}\n```',
    )
    assert await _parse_time_with_llm("表述") == datetime(2026, 10, 4, 9, 0)


async def test_python_dict_reply_tolerated(configured, monkeypatch):
    """回复为 python 字典字面量（单引号）时同样可解析。"""
    _install_fake_openai(
        monkeypatch, content="{'type': 'interval', 'value': 90, 'unit': 'minute'}"
    )
    trigger = await _parse_time_with_llm("每隔90分钟")
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval == timedelta(minutes=90)


async def test_malformed_reply(configured, monkeypatch):
    """回复无法解析为 JSON 时降级为 None。"""
    _install_fake_openai(monkeypatch, content="这不是一个字典")
    assert await _parse_time_with_llm("模糊表述") is None


async def test_unknown_type(configured, monkeypatch):
    _install_fake_openai(monkeypatch, content='{"type": "weekly", "value": 1}')
    assert await _parse_time_with_llm("模糊表述") is None


async def test_invalid_cron_params(configured, monkeypatch):
    """cron 参数非法时降级为 None。"""
    _install_fake_openai(
        monkeypatch, content='{"type": "cron", "params": {"hour": 99}}'
    )
    assert await _parse_time_with_llm("表述") is None


async def test_request_error_falls_back(configured, monkeypatch):
    """请求抛异常时降级为 None，不向外抛出。"""
    _install_fake_openai(monkeypatch, error=RuntimeError("网络错误"))
    assert await parsed_time_llm("明天") is None
    assert await _parse_time_with_llm("明天") is None


async def test_sdk_missing_falls_back(configured, monkeypatch):
    """openai SDK 未安装（导入失败）时降级为 None。"""
    monkeypatch.setitem(sys.modules, "openai", None)
    assert await parsed_time_llm("明天") is None


async def test_fallback_flows_through_unified_entry(monkeypatch):
    """兜底不再按「每」开头分流：各类文本统一进入同一个入口。"""
    import nonebot_plugin_remind.parse as parse_mod

    monkeypatch.setattr(parse_mod, "_parse_with_jionlp", lambda _text: None)
    calls: list[str] = []

    async def fake_llm(text: str):
        calls.append(text)
        return None

    monkeypatch.setattr(parse_mod, "_parse_time_with_llm", fake_llm)

    assert await parse_mod.parse_time("从下周一开始每天早上7点") is None
    assert await parse_mod.parse_time("明天下午3点") is None
    assert calls == ["从下周一开始每天早上7点", "明天下午3点"]


async def test_date_missing_or_bad_datetime(configured, monkeypatch):
    """date 回复缺少 datetime 或格式不正确时降级为 None。"""
    _install_fake_openai(monkeypatch, content='{"type": "date"}')
    assert await _parse_time_with_llm("表述") is None

    _install_fake_openai(monkeypatch, content='{"type": "date", "datetime": "明天"}')
    assert await _parse_time_with_llm("表述") is None


async def test_cron_missing_params(configured, monkeypatch):
    """cron 回复缺少 params 时降级为 None。"""
    _install_fake_openai(monkeypatch, content='{"type": "cron"}')
    assert await _parse_time_with_llm("表述") is None


async def test_interval_invalid_value(configured, monkeypatch):
    """interval 回复 value 非数字时降级为 None。"""
    _install_fake_openai(
        monkeypatch, content='{"type": "interval", "value": "半小时", "unit": "minute"}'
    )
    assert await _parse_time_with_llm("表述") is None


async def test_api_key_missing_skips_client(monkeypatch):
    """模型已配置但未配置 Key：客户端构建阶段静默跳过。"""
    monkeypatch.setattr(plugin_config, "remind_llm_model", "test-model")
    monkeypatch.setattr(plugin_config, "remind_llm_api_key", "")
    assert await parsed_time_llm("明天") is None


async def test_client_init_failure_falls_back(configured, monkeypatch):
    """客户端初始化抛错时降级为 None。"""
    _install_fake_openai(monkeypatch, client_error=RuntimeError("初始化失败"))
    assert await parsed_time_llm("明天") is None


async def test_empty_content_reply(configured, monkeypatch):
    """回复内容为空时降级为 None。"""
    _install_fake_openai(monkeypatch, content=None)
    assert await parsed_time_llm("明天") is None


async def test_unparsable_braces_reply(configured, monkeypatch):
    """带花括号但无法解析的回复降级为 None。"""
    _install_fake_openai(monkeypatch, content="{这不是合法数据}")
    assert await _parse_time_with_llm("表述") is None


async def test_non_dict_payload_reply(configured, monkeypatch):
    """解析结果不是字典（如集合字面量）时降级为 None。"""
    _install_fake_openai(monkeypatch, content="{1, 2, 3}")
    assert await _parse_time_with_llm("表述") is None
