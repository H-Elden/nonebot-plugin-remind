"""OneBot V11 假消息事件构造器（测试用）。

构造方式借鉴官方 uv 模板 fllesser/nonebot-plugin-template 的 tests/fake.py：
用 pydantic 动态子类化事件模型并给出默认字段，调用方可覆盖任意字段
（如 ``message=Message("...")``、``user_id=...``、``to_me=True``）。

注意：真实链路中适配器的 ``_check_at_me`` / ``_check_nickname`` 会在事件
进入匹配器前剥除 @机器人 / 昵称并置 ``to_me``；nonebug 的 ``receive_event``
不经过该层，因此测试消息按「剥除后」的形态构造（不含 @机器人 段，按需
显式传 ``to_me=True``）。
"""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import GroupMessageEvent as GroupMessageEventV11
    from nonebot.adapters.onebot.v11 import (
        PrivateMessageEvent as PrivateMessageEventV11,
    )


def fake_group_message_event_v11(**field) -> "GroupMessageEventV11":
    """构造一条 OneBot V11 群消息事件（默认群号 87654321、发送者 12345678）。"""
    import random

    from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
    from nonebot.adapters.onebot.v11.event import Reply, Sender
    from pydantic import create_model

    _Fake = create_model("_Fake", __base__=GroupMessageEvent)

    class FakeEvent(_Fake):
        time: int = 1_000_000
        self_id: int = 1
        post_type: Literal["message"] = "message"
        sub_type: str = "normal"
        user_id: int = 12_345_678
        message_type: Literal["group"] = "group"
        group_id: int = 87_654_321
        message_id: int = random.randint(1, 10_000_000)
        message: Message = Message("test")
        raw_message: str = "test"
        font: int = 0
        sender: Sender = Sender(card="", nickname="test", role="member")
        to_me: bool = False
        reply: Reply | None = None

    return FakeEvent(**field)


def fake_private_message_event_v11(**field) -> "PrivateMessageEventV11":
    """构造一条 OneBot V11 私聊消息事件（默认发送者 12345678）。"""
    import random

    from nonebot.adapters.onebot.v11 import Message, PrivateMessageEvent
    from nonebot.adapters.onebot.v11.event import Reply, Sender
    from pydantic import create_model

    _Fake = create_model("_Fake", __base__=PrivateMessageEvent)

    class FakeEvent(_Fake):
        time: int = 1_000_000
        self_id: int = 1
        post_type: Literal["message"] = "message"
        sub_type: Literal["friend"] = "friend"
        user_id: int = 12_345_678
        message_type: Literal["private"] = "private"
        message_id: int = random.randint(1, 10_000_000)
        message: Message = Message("test")
        raw_message: str = "test"
        font: int = 0
        sender: Sender = Sender(nickname="test")
        # onebot v11 适配器对私聊消息事件恒置 to_me=True
        to_me: bool = True
        reply: Reply | None = None

    return FakeEvent(**field)
