"""data_source 单元测试：到点发送与失败兜底、时间已过异常路径。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import cast

import jsonpickle
from nonebot.adapters.onebot.v11 import Event, Message, MessageSegment

import nonebot_plugin_remind.data_source as data_source


class _FakeBot:
    """记录各类发送的假 Bot；fail_first 时首次发送抛错（走兜底文案）。"""

    def __init__(self, *, fail_first: bool = False):
        self.group_sends: list[tuple[int, Message]] = []
        self.private_sends: list[tuple[int, Message]] = []
        self.sent: list = []
        self._fail_first = fail_first
        self._calls = 0

    async def send_group_msg(self, group_id: int, message: Message) -> None:
        self._calls += 1
        if self._fail_first and self._calls == 1:
            raise RuntimeError("发送失败")
        self.group_sends.append((group_id, message))

    async def send_private_msg(self, user_id: int, message: Message) -> None:
        self._calls += 1
        if self._fail_first and self._calls == 1:
            raise RuntimeError("发送失败")
        self.private_sends.append((user_id, message))

    async def send(self, event, message) -> None:
        self.sent.append(message)


def _patch_bot(monkeypatch, bot: _FakeBot) -> None:
    monkeypatch.setattr(data_source.nonebot, "get_bot", lambda: bot)


async def test_send_reminder_group_success(monkeypatch):
    bot = _FakeBot()
    _patch_bot(monkeypatch, bot)
    user_ids = Message(MessageSegment.at("all"))
    await data_source.send_reminder("no-such", user_ids, Message("内容"), True, 10001)
    assert bot.group_sends == [(10001, user_ids + Message("内容"))]


async def test_send_reminder_group_failure_fallback(monkeypatch):
    bot = _FakeBot(fail_first=True)
    _patch_bot(monkeypatch, bot)
    user_ids = Message(MessageSegment.at("all"))
    await data_source.send_reminder("no-such", user_ids, Message("内容"), True, 10001)
    assert len(bot.group_sends) == 1
    group_id, msg = bot.group_sends[0]
    assert group_id == 10001
    assert str(msg) == "[CQ:at,qq=all]\nRuntimeError: 发送失败\n内容"


async def test_send_reminder_private_variants(monkeypatch):
    bot = _FakeBot()
    _patch_bot(monkeypatch, bot)
    await data_source.send_reminder(
        "no-such", Message(), Message("内容"), False, 12345678
    )
    assert bot.private_sends == [(12345678, Message("内容"))]

    bot2 = _FakeBot(fail_first=True)
    _patch_bot(monkeypatch, bot2)
    await data_source.send_reminder(
        "no-such", Message(), Message("内容"), False, 12345678
    )
    assert len(bot2.private_sends) == 1
    _, msg = bot2.private_sends[0]
    assert str(msg) == "\nRuntimeError: 发送失败\n内容"


async def test_send_reminder_datetime_task_cleanup(isolated, monkeypatch):
    """单次任务发送后从任务集移除并落盘。"""
    tasks_file, task_info = isolated
    bot = _FakeBot()
    _patch_bot(monkeypatch, bot)
    task_info["t1"] = {
        "task_id": "t1",
        "reminder_user_id": "10001",
        "user_ids": Message(),
        "type": "datetime",
        "remind_time": datetime.now(),
        "reminder_message": Message("内容"),
        "is_group": False,
        "group_id": 12345678,
    }

    await data_source.send_reminder("t1", Message(), Message("内容"), False, 12345678)

    assert "t1" not in task_info
    saved = jsonpickle.decode(tasks_file.read_text(encoding="utf-8"))
    assert "t1" not in saved


async def test_set_reminder_past_time_reports_error(monkeypatch):
    """时间已过：捕获异常并向事件主体反馈错误文案。"""
    bot = _FakeBot()
    _patch_bot(monkeypatch, bot)
    event = cast(Event, SimpleNamespace(get_user_id=lambda: "10001"))
    state = {
        "user_ids": Message(),
        "remind_time": datetime.now() - timedelta(minutes=1),
        "reminder_message": Message("内容"),
    }

    await data_source.set_reminder(event, state)

    assert bot.sent == ["ValueError: 提醒时间已过，请设置未来的时间。"]
