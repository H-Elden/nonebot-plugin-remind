"""集成测试共用工具：事件构造、bot 助手、随机固定与期望消息。"""

from datetime import datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fake_event import fake_group_message_event_v11
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebug.mixin.process import MatcherContext

import nonebot_plugin_remind.data_source as data_source
from nonebot_plugin_remind.colloquial import colloquial_time

GROUP_ID = 87654321
USER_ID = 12345678

RemindTime = datetime | CronTrigger | IntervalTrigger


def group_event(
    message: str | Message,
    *,
    to_me: bool = False,
    user_id: int = USER_ID,
    group_id: int = GROUP_ID,
):
    """构造群消息事件；消息按「适配器剥除 @机器人 与昵称后」的形态传入。"""
    return fake_group_message_event_v11(
        message=message if isinstance(message, Message) else Message(message),
        user_id=user_id,
        group_id=group_id,
        to_me=to_me,
    )


def make_bot(ctx: MatcherContext):
    """按 nonebug 惯例创建适配器与已连接的假 Bot。"""
    adapter = ctx.create_adapter(base=OnebotV11Adapter)
    return ctx.create_bot(base=Bot, adapter=adapter)


def fixed_random(monkeypatch) -> None:
    """固定随机源：成功语与表情取第一项，随机秒数偏移取 0。"""
    monkeypatch.setattr(data_source.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(data_source.random, "randint", lambda a, b: 0)


def tomorrow_at(hour: int = 15) -> datetime:
    """按 jionlp 语义给出「明天 hour:00:00」（供断言与期望消息使用）。"""
    return (datetime.now() + timedelta(days=1)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


def success_message(remind_time: RemindTime, pron: str = "你") -> Message:
    """拼装与实现同序的成功反馈消息（配合 fixed_random 使用）。"""
    return (
        Message(MessageSegment.text("好的！"))
        + MessageSegment.face(314)
        + f"我会在{colloquial_time(remind_time)}准时提醒{pron}的！"
    )
