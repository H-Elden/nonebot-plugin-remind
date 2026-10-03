"""周期粒度测试：「每 N 秒/分钟/小时/天/周」间隔触发、展示与类型适配。"""

from datetime import timedelta

import jsonpickle
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from nonebot_plugin_remind.colloquial import colloquial_time
from nonebot_plugin_remind.parse import parse_time


async def test_interval_phrases():
    """无锚点的「每 N …」→ IntervalTrigger（jionlp 输出探针锁定）。"""
    cases = {
        "每30分钟": timedelta(minutes=30),
        "每半小时": timedelta(minutes=30),
        "每2小时": timedelta(hours=2),
        "每3小时": timedelta(hours=3),
        "每2天": timedelta(days=2),
        "每3天": timedelta(days=3),
        "每2周": timedelta(weeks=2),
        "每3周": timedelta(weeks=3),
        "每90秒": timedelta(seconds=90),
        "每隔3天": timedelta(days=3),
        "每隔2小时": timedelta(hours=2),
    }
    for text, expected in cases.items():
        trigger = await parse_time(text)
        assert isinstance(trigger, IntervalTrigger), f"{text} → {trigger!r}"
        assert trigger.interval == expected, f"{text} → {trigger.interval}"


async def test_bare_n1_phrases_become_intervals():
    """裸 N=1 表达（每分钟/每小时/每天/每周）原为解析失败，现补为 1 单位间隔。"""
    cases = {
        "每分钟": timedelta(minutes=1),
        "每小时": timedelta(hours=1),
        "每天": timedelta(days=1),
        "每周": timedelta(weeks=1),
    }
    for text, expected in cases.items():
        trigger = await parse_time(text)
        assert isinstance(trigger, IntervalTrigger), f"{text} → {trigger!r}"
        assert trigger.interval == expected


async def test_cron_phrases_unchanged():
    """带锚点表达维持 CronTrigger（行为兼容）。"""
    trigger = await parse_time("每天8:00")
    assert isinstance(trigger, CronTrigger)
    fields = {field.name: str(field) for field in trigger.fields}
    assert fields["hour"] == "8"

    trigger = await parse_time("每周三14:00")
    assert isinstance(trigger, CronTrigger)
    fields = {field.name: str(field) for field in trigger.fields}
    assert fields["day_of_week"] in {"2", "wed"}
    assert fields["hour"] == "14"

    trigger = await parse_time("每月15号9:30")
    assert isinstance(trigger, CronTrigger)
    fields = {field.name: str(field) for field in trigger.fields}
    assert fields["day"] == "15"


async def test_month_year_intervals_still_unsupported():
    assert await parse_time("每2个月") is None


def test_colloquial_interval_display():
    assert colloquial_time(IntervalTrigger(days=3)) == "每隔 3 天"
    assert colloquial_time(IntervalTrigger(weeks=2)) == "每隔 2 周"
    assert colloquial_time(IntervalTrigger(hours=2)) == "每隔 2 小时"
    assert colloquial_time(IntervalTrigger(minutes=30)) == "每隔 30 分钟"
    assert colloquial_time(IntervalTrigger(seconds=90)) == "每隔 90 秒"


def test_interval_trigger_jsonpickle_roundtrip():
    """IntervalTrigger 可随数据文件序列化与恢复。"""
    trigger = IntervalTrigger(days=3)
    decoded = jsonpickle.decode(jsonpickle.encode(trigger))
    assert isinstance(decoded, IntervalTrigger)
    assert decoded.interval == trigger.interval


def test_recurring_task_types_filter(isolated):
    """列表/删除的循环任务过滤同时涵盖 CronTrigger 与 IntervalTrigger。"""
    _, task_info = isolated
    task_info["a"] = {
        "task_id": "a",
        "reminder_user_id": "u1",
        "type": "CronTrigger",
        "group_id": 1,
    }
    task_info["b"] = {
        "task_id": "b",
        "reminder_user_id": "u1",
        "type": "IntervalTrigger",
        "group_id": 1,
    }
    task_info["c"] = {
        "task_id": "c",
        "reminder_user_id": "u1",
        "type": "datetime",
        "group_id": 1,
    }

    from nonebot_plugin_remind.utils import get_user_cron_tasks

    got = {t["task_id"] for t in get_user_cron_tasks("u1", None)}
    assert got == {"a", "b"}
