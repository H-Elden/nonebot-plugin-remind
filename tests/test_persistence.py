"""数据持久化加固测试：原子写、容错载入、删除与保存时序。

隔离方式见 conftest 的 isolated 夹具。
"""

import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import cast

import jsonpickle
import pytest
from apscheduler.triggers.cron import CronTrigger
from nonebot.adapters.onebot.v11 import Event, Message
from nonebot.matcher import Matcher
from nonebot_plugin_apscheduler import scheduler

import nonebot_plugin_remind
import nonebot_plugin_remind.data_source as data_source
import nonebot_plugin_remind.utils as utils


def test_save_is_atomic_and_leaves_no_tmp(isolated):
    tasks_file, task_info = isolated
    task_info["t1"] = {"task_id": "t1"}
    utils.save_tasks_to_file()

    saved = jsonpickle.decode(tasks_file.read_text(encoding="utf-8"))
    assert saved == {"t1": {"task_id": "t1"}}
    assert not list(tasks_file.parent.glob("*.tmp"))


def test_save_failure_keeps_old_file(isolated, monkeypatch):
    """写盘中途失败时，磁盘上的原文件保持完好。"""
    tasks_file, task_info = isolated
    old_content = str(jsonpickle.encode({"old": {"task_id": "old"}}, indent=4))
    tasks_file.write_text(old_content, encoding="utf-8")
    task_info["t1"] = {"task_id": "t1"}

    def boom(src, dst):
        raise OSError("模拟磁盘错误")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        utils.save_tasks_to_file()

    assert tasks_file.read_text(encoding="utf-8") == old_content
    assert not list(tasks_file.parent.glob("*.tmp"))


async def test_load_valid_file_restores_tasks(isolated, logs):
    tasks_file, task_info = isolated
    payload = {
        "t1": {
            "task_id": "t1",
            "reminder_user_id": "10001",
            "user_ids": Message("[CQ:at,qq=10001]"),
            "type": "datetime",
            "remind_time": datetime.now() + timedelta(hours=1),
            "reminder_message": Message("测试内容"),
            "is_group": False,
            "group_id": 10001,
        }
    }
    tasks_file.write_text(str(jsonpickle.encode(payload, indent=4)), encoding="utf-8")

    await nonebot_plugin_remind.load_tasks()

    assert "t1" in task_info
    assert scheduler.get_job("t1") is not None
    scheduler.remove_job("t1")
    assert any("已载入 1 个任务" in m for m in logs), logs


async def test_load_corrupt_file_backs_up_and_continues(isolated):
    """文件损坏时转存备份、以空任务集继续启动。"""
    tasks_file, task_info = isolated
    tasks_file.write_text("{ 这不是合法数据", encoding="utf-8")

    await nonebot_plugin_remind.load_tasks()

    # 以空任务集继续：文件被重建为可解析的空字典
    assert task_info == {}
    assert jsonpickle.decode(tasks_file.read_text(encoding="utf-8")) == {}
    # 损坏文件被转存为备份
    backups = list(tasks_file.parent.glob("remind_tasks.corrupt-*.json"))
    assert len(backups) == 1
    assert "这不是合法数据" in backups[0].read_text(encoding="utf-8")


async def test_delete_persists_on_midway_error(isolated, monkeypatch):
    """批量删除中途异常时，已删除的部分也要落盘（防重启后复活）。"""
    tasks_file, task_info = isolated
    task_info["t1"] = {
        "task_id": "t1",
        "reminder_message": Message("内容一"),
        "user_ids": Message(),
        "is_group": False,
        "group_id": 10001,
        "type": "datetime",
        "remind_time": datetime.now() + timedelta(hours=1),
        "reminder_user_id": "10001",
    }
    fake_job = SimpleNamespace(remove=lambda: None)
    monkeypatch.setattr(
        scheduler, "get_job", lambda tid: fake_job if tid == "t1" else None
    )

    user_tasks = [task_info["t1"]]
    with pytest.raises(ValueError):
        await nonebot_plugin_remind._delete_tasks(
            cast(type[Matcher], SimpleNamespace()), user_tasks, [0, 5]
        )

    assert "t1" not in task_info
    saved = jsonpickle.decode(tasks_file.read_text(encoding="utf-8"))
    assert "t1" not in saved


async def test_set_reminder_saves_before_success_message(isolated, monkeypatch):
    """成功反馈发送失败时，提醒任务仍已落盘。"""
    tasks_file, task_info = isolated
    order: list[str] = []
    real_save = data_source.save_tasks_to_file

    def recording_save():
        order.append("save")
        real_save()

    monkeypatch.setattr(data_source, "save_tasks_to_file", recording_save)

    async def fake_set_date(event, state):
        order.append("schedule")
        task_info["t-new"] = {
            "task_id": "t-new",
            "reminder_user_id": event.get_user_id(),
            "user_ids": state["user_ids"],
            "type": "datetime",
            "remind_time": state["remind_time"],
            "reminder_message": state["reminder_message"],
            "is_group": False,
            "group_id": 10001,
        }

    monkeypatch.setattr(data_source, "set_date_reminder", fake_set_date)

    class FakeBot:
        async def send(self, event, msg):
            order.append("send")
            raise RuntimeError("模拟发送失败")

    monkeypatch.setattr(data_source.nonebot, "get_bot", lambda: FakeBot())

    event = cast(Event, SimpleNamespace(get_user_id=lambda: "10001"))
    state = {
        "user_ids": Message(),
        "remind_time": datetime.now() + timedelta(hours=1),
        "reminder_message": Message("内容"),
    }
    with pytest.raises(RuntimeError):
        await data_source.set_reminder(event, state)

    assert order == ["schedule", "save", "send"]
    saved = jsonpickle.decode(tasks_file.read_text(encoding="utf-8"))
    assert "t-new" in saved


async def test_delete_missing_task_raises_business_error(isolated, monkeypatch):
    """任务不存在时抛业务异常 TaskGoneError（与系统异常区分）。"""
    _, task_info = isolated
    task_info["t1"] = {
        "task_id": "t1",
        "reminder_message": Message("内容一"),
        "user_ids": Message(),
        "is_group": False,
        "group_id": 10001,
        "type": "datetime",
        "remind_time": datetime.now() + timedelta(hours=1),
        "reminder_user_id": "10001",
    }
    monkeypatch.setattr(scheduler, "get_job", lambda tid: None)

    with pytest.raises(nonebot_plugin_remind.TaskGoneError):
        await nonebot_plugin_remind._delete_tasks(
            cast(type[Matcher], SimpleNamespace()), [task_info["t1"]], [0]
        )


def test_has_legacy_tasks_detection():
    """0.1.x 旧格式三种特征与非字典值的识别。"""
    from nonebot_plugin_remind import _has_legacy_tasks

    assert _has_legacy_tasks({}) is False
    assert _has_legacy_tasks({"t1": {"type": "datetime"}}) is False
    # 无 type 字段
    assert _has_legacy_tasks({"t1": {"remind_time": "2026-10-10 09:00:00"}}) is True
    # reminder_message 为字符串
    assert (
        _has_legacy_tasks({"t1": {"type": "datetime", "reminder_message": "文本"}})
        is True
    )
    # user_ids 为 CQ 码字符串
    assert (
        _has_legacy_tasks({"t1": {"type": "datetime", "user_ids": "[CQ:at,qq=1]"}})
        is True
    )
    # 非字典任务
    assert _has_legacy_tasks({"t1": "不是字典"}) is True


async def test_load_legacy_file_backs_up_and_continues(isolated):
    """0.1.x 旧格式文件不再迁移：转存备份、以空任务集继续启动。"""
    tasks_file, task_info = isolated
    legacy_payload = {
        "t1": {
            "reminder_user_id": "10001",
            "user_ids": "[CQ:at,qq=10001] ",
            "remind_time": "2026-10-10 09:00:00",
            "reminder_message": "旧版内容",
            "is_group": False,
            "group_id": 10001,
        }
    }
    tasks_file.write_text(
        str(jsonpickle.encode(legacy_payload, indent=4)), encoding="utf-8"
    )

    await nonebot_plugin_remind.load_tasks()

    # 旧任务未被载入，文件被重建为空任务集
    assert task_info == {}
    assert jsonpickle.decode(tasks_file.read_text(encoding="utf-8")) == {}
    # 旧文件被转存为备份
    backups = list(tasks_file.parent.glob("remind_tasks.corrupt-*.json"))
    assert len(backups) == 1
    assert "旧版内容" in backups[0].read_text(encoding="utf-8")


async def test_load_expired_task_marked_for_makeup(isolated, monkeypatch, logs):
    """过期单次任务载入时写入补发说明并顺延执行时间；日志按「补发」而非「删除」描述。"""
    tasks_file, task_info = isolated
    monkeypatch.setattr(nonebot_plugin_remind.random, "randint", lambda a, b: 10)
    old_time = datetime.now() - timedelta(hours=1)
    payload = {
        "t1": {
            "task_id": "t1",
            "reminder_user_id": "10001",
            "user_ids": Message("[CQ:at,qq=10001]"),
            "type": "datetime",
            "remind_time": old_time,
            "reminder_message": Message("测试内容"),
            "is_group": False,
            "group_id": 10001,
        }
    }
    tasks_file.write_text(str(jsonpickle.encode(payload, indent=4)), encoding="utf-8")

    await nonebot_plugin_remind.load_tasks()

    task = task_info["t1"]
    assert "此提醒任务已超时1小时。" in str(task["reminder_message"])
    assert f"原定提醒时间为：{old_time.strftime('%Y-%m-%d %H:%M')}" in str(
        task["reminder_message"]
    )
    assert abs(task["remind_time"] - (datetime.now() + timedelta(seconds=10))) < (
        timedelta(seconds=5)
    )
    assert any("已载入 0 个任务，1 个错过时点的提醒已补发" in m for m in logs), logs
    assert not any("删除" in m and "过时任务" in m for m in logs), logs
    scheduler.remove_job("t1")


async def test_load_valid_cron_task_restored(isolated):
    """载入含循环任务的合法文件，按触发器恢复调度。"""
    tasks_file, task_info = isolated
    payload = {
        "c1": {
            "task_id": "c1",
            "reminder_user_id": "10001",
            "user_ids": Message("[CQ:at,qq=10001]"),
            "type": "CronTrigger",
            "remind_time": CronTrigger(hour=8, minute=0),
            "reminder_message": Message("循环内容"),
            "is_group": False,
            "group_id": 10001,
        }
    }
    tasks_file.write_text(str(jsonpickle.encode(payload, indent=4)), encoding="utf-8")

    await nonebot_plugin_remind.load_tasks()

    assert "c1" in task_info
    assert scheduler.get_job("c1") is not None
    scheduler.remove_job("c1")
