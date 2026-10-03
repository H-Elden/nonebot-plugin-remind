"""parse 模块单元测试：jionlp 结果转换与边界分支。"""

from datetime import datetime, timedelta

import nonebot_plugin_remind.parse as parse_mod


async def test_empty_inputs():
    assert await parse_mod.parse_time("") is None
    assert await parse_mod.parse_time("   ") is None
    assert await parse_mod.extract_time_and_message("") == (None, "")


def test_delta_to_datetime_variants():
    now = datetime.now()
    out = parse_mod._delta_to_datetime({"hour": 0.5})
    assert out is not None
    assert abs((out - now) - timedelta(minutes=30)) < timedelta(seconds=5)

    out = parse_mod._delta_to_datetime([{"minute": 10}, {"minute": 20}])
    assert out is not None
    assert abs((out - now) - timedelta(minutes=10)) < timedelta(seconds=5)

    out = parse_mod._delta_to_datetime({"month": 1})
    assert out is not None
    assert abs((out - now) - timedelta(days=30)) < timedelta(seconds=5)

    out = parse_mod._delta_to_datetime({"year": 1})
    assert out is not None
    assert abs((out - now) - timedelta(days=365)) < timedelta(seconds=5)

    assert parse_mod._delta_to_datetime({}) is None


def test_build_cron_params_guards():
    pt = datetime(2026, 10, 8, 8, 30)
    assert parse_mod._build_cron_params({"hour": 1}, pt) == {"minute": 30}
    assert parse_mod._build_cron_params({"hour": 3}, pt) == {}
    assert parse_mod._build_cron_params({"day": 1}, pt) == {"hour": 8, "minute": 30}
    assert parse_mod._build_cron_params({"day": 7}, pt) == {
        "day_of_week": pt.weekday(),
        "hour": 8,
        "minute": 30,
    }
    assert parse_mod._build_cron_params({"day": 3}, pt) == {}
    assert parse_mod._build_cron_params({"month": 1}, pt) == {
        "day": 8,
        "hour": 8,
        "minute": 30,
    }
    assert parse_mod._build_cron_params({"month": 2}, pt) == {}
    assert parse_mod._build_cron_params({"year": 1}, pt) == {
        "month": 10,
        "day": 8,
        "hour": 8,
        "minute": 30,
    }
    assert parse_mod._build_cron_params({"second": 5}, pt) == {}


def test_extract_point_time_variants():
    assert parse_mod._extract_point_time(None) is None
    assert parse_mod._extract_point_time({}) is None
    assert parse_mod._extract_point_time({"time": []}) is None
    assert parse_mod._extract_point_time({"time": ["不是时间"]}) is None
    assert parse_mod._extract_point_time({"time": ["2026-10-08 08:30:00"]}) == datetime(
        2026, 10, 8, 8, 30
    )


def test_period_to_trigger_edges():
    assert parse_mod._period_to_trigger({}) is None
    assert parse_mod._period_to_trigger({"delta": {}, "point": None}) is None
    assert (
        parse_mod._period_to_trigger(
            {"delta": {"hour": 1}, "point": {"time": ["不是时间"]}}
        )
        is None
    )


def test_parse_with_jionlp_edges(monkeypatch):
    monkeypatch.setattr(parse_mod.jio, "parse_time", lambda *a, **k: None)
    assert parse_mod._parse_with_jionlp("x") is None

    def _boom(*a, **k):
        raise RuntimeError("解析失败")

    monkeypatch.setattr(parse_mod.jio, "parse_time", _boom)
    assert parse_mod._parse_with_jionlp("x") is None

    monkeypatch.setattr(
        parse_mod.jio, "parse_time", lambda *a, **k: {"type": 123, "time": "x"}
    )
    assert parse_mod._parse_with_jionlp("x") is None

    monkeypatch.setattr(
        parse_mod.jio, "parse_time", lambda *a, **k: {"type": "未知类型", "time": "x"}
    )
    assert parse_mod._parse_with_jionlp("x") is None


async def test_extract_time_exception(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("ner 异常")

    monkeypatch.setattr(parse_mod.jio.ner, "extract_time", _boom)
    assert await parse_mod.extract_time_and_message("明天开会") == (None, "明天开会")


async def test_extract_time_entity_but_parse_fails(monkeypatch):
    async def _none(_text: str):
        return None

    monkeypatch.setattr(parse_mod, "parse_time", _none)
    parsed, remaining = await parse_mod.extract_time_and_message("明天开会")
    assert parsed is None
    assert remaining == "明天开会"


def test_parse_timestamp_errors():
    assert parse_mod._parse_timestamp([]) is None
    assert parse_mod._parse_timestamp(["不是时间"]) is None
    assert parse_mod._parse_timestamp([None]) is None


def test_delta_to_datetime_invalid_value():
    assert parse_mod._delta_to_datetime({"day": "坏值"}) is None


def test_build_interval_trigger_guards():
    assert parse_mod._build_interval_trigger({"month": 1}) is None
    assert parse_mod._build_interval_trigger({"year": 1}) is None
    assert parse_mod._build_interval_trigger({"second": 0.5}) is None
    assert parse_mod._build_interval_trigger({}) is None
    assert parse_mod._build_interval_trigger({"minute": 30}) is not None


def test_build_cron_params_year_guard():
    pt = datetime(2026, 10, 8, 8, 30)
    assert parse_mod._build_cron_params({"year": 2}, pt) == {}


def test_period_to_trigger_construction_error(monkeypatch):
    class _BoomCron:
        def __init__(self, **kwargs):
            raise ValueError("构造失败")

    monkeypatch.setattr(parse_mod, "CronTrigger", _BoomCron)
    assert (
        parse_mod._period_to_trigger(
            {"delta": {"day": 1}, "point": {"time": ["2026-10-08 08:30:00"]}}
        )
        is None
    )
