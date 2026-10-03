"""大模型兜底链路单元测试：mock OpenAI 兼容接口，不发起真实请求。"""

import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace

import pytest

from nonebot_plugin_remind.config import plugin_config
from nonebot_plugin_remind.llm import parsed_cron_time_llm, parsed_datetime_llm
from nonebot_plugin_remind.parse import _parse_cron_with_llm, _parse_date_with_llm


@pytest.fixture
def configured(monkeypatch):
    """临时配置四项大模型参数（默认未配置）。"""
    monkeypatch.setattr(plugin_config, "llm_api_key", "test-key")
    monkeypatch.setattr(plugin_config, "llm_base_url", "")
    monkeypatch.setattr(plugin_config, "llm_model", "test-datetime-model")
    monkeypatch.setattr(plugin_config, "llm_model_cron", "test-cron-model")


def _install_fake_openai(monkeypatch, *, content=None, error=None):
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
            calls["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    fake_module = ModuleType("openai")
    fake_module.AsyncOpenAI = _FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return calls


async def test_unconfigured_skips_silently(monkeypatch, caplog):
    """未配置 API Key 时静默跳过，不产生 warning 日志。"""
    monkeypatch.setattr(plugin_config, "llm_api_key", "")
    with caplog.at_level("WARNING"):
        assert await parsed_datetime_llm("明天下午3点") is None
        assert await parsed_cron_time_llm("每天8点") is None
    assert not caplog.records


async def test_empty_text_returns_none(configured, monkeypatch):
    _install_fake_openai(monkeypatch, content="2026-01-01 00:00")
    assert await parsed_datetime_llm("") is None
    assert await parsed_cron_time_llm("") is None


async def test_datetime_success(configured, monkeypatch):
    """配置齐全且 SDK 可用时，单次解析走单次模型并返回文本。"""
    calls = _install_fake_openai(monkeypatch, content="2026-10-04 09:00")
    assert await parsed_datetime_llm("国庆假期早上9点") == "2026-10-04 09:00"
    assert calls["create_kwargs"]["model"] == "test-datetime-model"
    assert calls["client_kwargs"]["api_key"] == "test-key"


async def test_parse_datetime_integration(configured, monkeypatch):
    """parse 层的包装：文本结果被解析为 datetime。"""
    _install_fake_openai(monkeypatch, content="2026-10-04 09:00")
    assert await _parse_date_with_llm("某表述") == datetime(2026, 10, 4, 9, 0)


async def test_datetime_model_reply_none(configured, monkeypatch):
    """模型回复 "None" 表示无法解析。"""
    _install_fake_openai(monkeypatch, content="None")
    assert await _parse_date_with_llm("无法解析的表述") is None


async def test_request_error_falls_back(configured, monkeypatch):
    """请求抛异常时降级为 None，不向外抛出。"""
    _install_fake_openai(monkeypatch, error=RuntimeError("网络错误"))
    assert await parsed_datetime_llm("明天") is None
    assert await _parse_date_with_llm("明天") is None


async def test_sdk_missing_falls_back(configured, monkeypatch):
    """openai SDK 未安装（导入失败）时降级为 None。"""
    monkeypatch.setitem(sys.modules, "openai", None)
    assert await parsed_datetime_llm("明天") is None


async def test_cron_success(configured, monkeypatch):
    """循环解析走循环模型，参数字典被构建为 CronTrigger。"""
    calls = _install_fake_openai(monkeypatch, content="{'hour': 8, 'minute': 30}")
    trigger = await _parse_cron_with_llm("每天早上8点半")
    assert trigger is not None
    fields = {field.name: str(field) for field in trigger.fields}
    assert fields["hour"] == "8"
    assert fields["minute"] == "30"
    assert calls["create_kwargs"]["model"] == "test-cron-model"


async def test_cron_model_reply_none(configured, monkeypatch):
    _install_fake_openai(monkeypatch, content="None")
    assert await _parse_cron_with_llm("模糊表述") is None


async def test_cron_malformed_params(configured, monkeypatch):
    """模型返回无法解析的文本时降级为 None。"""
    _install_fake_openai(monkeypatch, content="这不是一个字典")
    assert await _parse_cron_with_llm("模糊表述") is None
