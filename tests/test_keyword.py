"""关键词「提醒」流的 nonebug 集成测试（含边缘格式现状锁定）。"""

from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebug import App
from support import (
    USER_ID,
    fixed_random,
    group_event,
    make_bot,
    success_message,
    tomorrow_at,
)

import nonebot_plugin_remind as plugin
from nonebot_plugin_remind.config import plugin_config


def _only_task(task_info: dict) -> dict:
    assert len(task_info) == 1
    return next(iter(task_info.values()))


async def test_keyword_time_first_order(app: App, isolated, monkeypatch):
    """模式1：时间在前（明天下午3点提醒我开会）。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    event = group_event("明天下午3点提醒我开会", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target))
        ctx.receive_event(bot, event)

    task = _only_task(task_info)
    assert task["remind_time"] == target
    assert str(task["reminder_message"]) == "开会"
    assert str(task["user_ids"]) == f"[CQ:at,qq={USER_ID}]"


async def test_keyword_person_first_order(app: App, isolated, monkeypatch):
    """模式2：提醒在前（提醒我明天下午3点去开会），时间从剩余文本中提取。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    event = group_event("提醒我明天下午3点去开会", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target))
        ctx.receive_event(bot, event)

    task = _only_task(task_info)
    assert task["remind_time"] == target
    assert str(task["reminder_message"]) == "去开会"


async def test_keyword_all_then_message(app: App, isolated, monkeypatch):
    """「所有人」等价于 @全体成员。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    event = group_event("明天下午3点提醒所有人开会", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target, pron="你们"))
        ctx.receive_event(bot, event)

    task = _only_task(task_info)
    assert str(task["user_ids"]) == "[CQ:at,qq=all]"
    assert str(task["reminder_message"]) == "开会"
    assert task["is_group"] is True


async def test_keyword_multi_persons(app: App, isolated, monkeypatch):
    """「我和@用户1 @用户2」多提醒人。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    message = (
        Message("明天下午3点提醒我和")
        + MessageSegment.at(111)
        + MessageSegment.at(222)
        + "开会"
    )
    event = group_event(message, to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target, pron="你们"))
        ctx.receive_event(bot, event)

    task = _only_task(task_info)
    assert str(task["user_ids"]) == f"[CQ:at,qq={USER_ID}][CQ:at,qq=111][CQ:at,qq=222]"
    assert str(task["reminder_message"]) == "开会"


async def test_keyword_edge_he_residue(app: App, isolated, monkeypatch):
    """锁定现状：「我和」后接纯文本时残留「和」字（本轮不改行为）。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    event = group_event("明天下午3点提醒我和朋友吃饭", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target))
        ctx.receive_event(bot, event)

    task = _only_task(task_info)
    assert str(task["reminder_message"]) == "和朋友吃饭"
    assert str(task["user_ids"]) == f"[CQ:at,qq={USER_ID}]"


async def test_keyword_edge_at_joined_into_message(app: App, isolated, monkeypatch):
    """锁定现状：「我 xxx @用户」时 at 段并入消息而非被提醒人（本轮不改行为）。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    message = Message("明天下午3点提醒我开会") + MessageSegment.at(111)
    event = group_event(message, to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target))
        ctx.receive_event(bot, event)

    task = _only_task(task_info)
    assert str(task["reminder_message"]) == "开会[CQ:at,qq=111]"
    assert str(task["user_ids"]) == f"[CQ:at,qq={USER_ID}]"


async def test_keyword_error_no_person(app: App, isolated, monkeypatch):
    """未匹配到提醒人时的提示。"""
    _, task_info = isolated
    monkeypatch.setattr(plugin_config, "remind_keyword_error", True)

    event = group_event("明天下午3点提醒开会", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, "关键词【提醒】触发：未匹配到提醒人")
        ctx.receive_event(bot, event)

    assert task_info == {}


async def test_keyword_error_not_text_first(app: App, isolated, monkeypatch):
    """消息以 at 开头（非文本）时的提示。"""
    _, task_info = isolated
    monkeypatch.setattr(plugin_config, "remind_keyword_error", True)

    message = Message(MessageSegment.at(999)) + "16:00提醒我开会"
    event = group_event(message, to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, "关键词【提醒】触发：消息应当以文本开头")
        ctx.receive_event(bot, event)

    assert task_info == {}


async def test_keyword_error_no_time(app: App, isolated, monkeypatch):
    """模式2 中提取不到时间时的提示。"""
    _, task_info = isolated
    monkeypatch.setattr(plugin_config, "remind_keyword_error", True)

    event = group_event("提醒我去吃饭", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, "关键词【提醒】触发：未匹配到时间")
        ctx.receive_event(bot, event)

    assert task_info == {}


async def test_keyword_person_collected_from_following_at(
    app: App, isolated, monkeypatch
):
    """「时间+提醒」后紧接 @用户：空文本分支从后续段收集被提醒人。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    message = Message("明天下午3点提醒") + MessageSegment.at(111) + "开会"
    event = group_event(message, to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target, pron="他"))
        ctx.receive_event(bot, event)

    task = _only_task(task_info)
    assert str(task["user_ids"]) == "[CQ:at,qq=111]"
    assert str(task["reminder_message"]) == "开会"


async def test_keyword_all_keyword_target(app: App, isolated, monkeypatch):
    """「all」写法同样等价于 @全体成员。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    event = group_event("明天下午3点提醒all开会", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target, pron="你们"))
        ctx.receive_event(bot, event)

    task = _only_task(task_info)
    assert str(task["user_ids"]) == "[CQ:at,qq=all]"
    assert str(task["reminder_message"]) == "开会"


async def test_keyword_error_keyword_position(app: App, isolated, monkeypatch):
    """「提醒」不在首个文本段时提示位置错误。"""
    _, task_info = isolated
    monkeypatch.setattr(plugin_config, "remind_keyword_error", True)

    message = Message("你好啊") + "提醒我"
    event = group_event(message, to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, "关键词【提醒】触发：“提醒”不在正确的位置")
        ctx.receive_event(bot, event)

    assert task_info == {}


async def test_keyword_error_no_person_in_person_first_mode(
    app: App, isolated, monkeypatch
):
    """模式2 下人称也解析失败时提示未匹配到提醒人。"""
    _, task_info = isolated
    monkeypatch.setattr(plugin_config, "remind_keyword_error", True)

    event = group_event("提醒看看", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, "关键词【提醒】触发：未匹配到提醒人")
        ctx.receive_event(bot, event)

    assert task_info == {}


async def test_keyword_error_person_without_time(app: App, isolated, monkeypatch):
    """模式2 下人称后没有内容时提示未匹配到时间。"""
    _, task_info = isolated
    monkeypatch.setattr(plugin_config, "remind_keyword_error", True)

    event = group_event("提醒我", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, "关键词【提醒】触发：未匹配到时间")
        ctx.receive_event(bot, event)

    assert task_info == {}


async def test_keyword_error_empty_message(app: App, isolated, monkeypatch):
    """被提醒人已匹配但消息为空时提示未匹配到提醒信息。"""
    _, task_info = isolated
    monkeypatch.setattr(plugin_config, "remind_keyword_error", True)

    message = Message("明天下午3点提醒") + MessageSegment.at(111)
    event = group_event(message, to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, "关键词【提醒】触发：未匹配到提醒信息")
        ctx.receive_event(bot, event)

    assert task_info == {}
