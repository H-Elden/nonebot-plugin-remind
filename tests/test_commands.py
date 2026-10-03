"""/remind 命令流、列表与删除闭环的 nonebug 集成测试。"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import jsonpickle
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fake_event import fake_private_message_event_v11
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot_plugin_apscheduler import scheduler
from nonebug import App
from support import (
    GROUP_ID,
    USER_ID,
    fixed_random,
    group_event,
    make_bot,
    success_message,
    tomorrow_at,
)

import nonebot_plugin_remind as plugin
from nonebot_plugin_remind.colloquial import colloquial_time


async def test_remind_command_full_args(app: App, isolated, monkeypatch):
    """完整参数一步设置：/remind 时间,消息。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    event = group_event("/remind 明天下午3点,开会")
    async with app.test_matcher(plugin.remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target))
        ctx.receive_event(bot, event)

    assert len(task_info) == 1
    task = next(iter(task_info.values()))
    assert task["type"] == "datetime"
    assert task["remind_time"] == target
    assert str(task["reminder_message"]) == "开会"
    assert str(task["user_ids"]) == f"[CQ:at,qq={USER_ID}]"
    assert task["is_group"] is True
    assert task["group_id"] == GROUP_ID


async def test_remind_two_step_flow(app: App, isolated, monkeypatch):
    """两步问答：/remind → 时间 → 消息。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    e1 = group_event("/remind")
    e2 = group_event("明天下午3点")
    e3 = group_event("开会")
    async with app.test_matcher(plugin.remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(
            e1, '提醒时间？支持自然语言，如"明天下午3点"、"每天8:00"。'
        )
        ctx.receive_event(bot, e1)
        ctx.should_rejected()
        ctx.should_call_send(e2, "提醒信息？请输入您想要发送的信息。")
        ctx.receive_event(bot, e2)
        ctx.should_rejected()
        ctx.should_call_send(e3, success_message(target))
        ctx.receive_event(bot, e3)

    assert len(task_info) == 1
    task = next(iter(task_info.values()))
    assert task["remind_time"] == target
    assert str(task["reminder_message"]) == "开会"


async def test_remind_cancel_flow(app: App, isolated):
    """问答中发送「取消」中止设置。"""
    _, task_info = isolated

    e1 = group_event("/remind")
    e2 = group_event("取消")
    async with app.test_matcher(plugin.remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(
            e1, '提醒时间？支持自然语言，如"明天下午3点"、"每天8:00"。'
        )
        ctx.receive_event(bot, e1)
        ctx.should_rejected()
        ctx.should_call_send(e2, "已取消提醒设置。")
        ctx.receive_event(bot, e2)
        ctx.should_finished()

    assert task_info == {}


async def test_remind_invalid_time_then_recover(app: App, isolated, monkeypatch):
    """时间无法解析时提示重输，随后可继续完成设置。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    e1 = group_event("/remind")
    e2 = group_event("哈哈哈哈哈")
    e3 = group_event("明天下午3点")
    e4 = group_event("开会")
    reject_text = (
        "时间格式不正确。请重新输入或发送“取消”中止交互。\n可尝试以下格式：\n"
        "支持格式如：14:30、明天下午3点、半小时后、每天8:00 等"
    )
    async with app.test_matcher(plugin.remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(
            e1, '提醒时间？支持自然语言，如"明天下午3点"、"每天8:00"。'
        )
        ctx.receive_event(bot, e1)
        ctx.should_rejected()
        ctx.should_call_send(e2, reject_text)
        ctx.receive_event(bot, e2)
        ctx.should_rejected()
        ctx.should_call_send(e3, "提醒信息？请输入您想要发送的信息。")
        ctx.receive_event(bot, e3)
        ctx.should_rejected()
        ctx.should_call_send(e4, success_message(target))
        ctx.receive_event(bot, e4)

    assert len(task_info) == 1


async def test_remind_multi_at_args(app: App, isolated, monkeypatch):
    """命令行内多个 @：按 at 段指定被提醒人（位于时间文本之前）。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    message = (
        Message("/remind ")
        + MessageSegment.at(111)
        + MessageSegment.at(222)
        + "明天下午3点,开会"
    )
    event = group_event(message)
    async with app.test_matcher(plugin.remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(event, success_message(target, pron="他们"))
        ctx.receive_event(bot, event)

    assert len(task_info) == 1
    task = next(iter(task_info.values()))
    assert str(task["user_ids"]) == "[CQ:at,qq=111][CQ:at,qq=222]"


async def test_remind_list_delete_loop(app: App, isolated, monkeypatch):
    """设置 → 列表 → 删除完整闭环。"""
    tasks_file, task_info = isolated
    fixed_random(monkeypatch)
    target = tomorrow_at()

    # 1) 设置
    e1 = group_event("/remind 明天下午3点,开会")
    async with app.test_matcher(plugin.remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e1, success_message(target))
        ctx.receive_event(bot, e1)
    assert len(task_info) == 1

    # 2) 列表（at 段无昵称，走群成员查询 API）
    members = [{"user_id": USER_ID, "card": "", "nickname": "小明"}]
    e2 = group_event("/提醒列表")
    expected_time = target.strftime("%Y/%m/%d %H:%M")
    async with app.test_matcher(plugin.list_reminds) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_api(
            "get_group_member_list", {"group_id": GROUP_ID}, result=members
        )
        ctx.should_call_send(
            e2,
            Message(
                f"您的提醒任务列表:\n01 时间: {expected_time}, 内容: [at 小明]开会"
            ),
        )
        ctx.receive_event(bot, e2)

    # 3) 删除
    e3 = group_event("/删除提醒 1")
    async with app.test_matcher(plugin.del_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_api(
            "get_group_member_list", {"group_id": GROUP_ID}, result=members
        )
        # 期望消息包裹为 Message：含 [at xx] 文本时 str 比较会走 CQ 转义
        ctx.should_call_send(e3, Message("成功删除以下提醒任务！\n01  [at 小明]开会"))
        ctx.receive_event(bot, e3)

    assert task_info == {}
    assert jsonpickle.decode(tasks_file.read_text(encoding="utf-8")) == {}


async def test_del_remind_out_of_range(app: App, isolated):
    """删除序号超出范围时的参数错误提示。"""
    _, task_info = isolated

    e = group_event("/删除提醒 9")
    async with app.test_matcher(plugin.del_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e, "参数不正确：序号超出范围。")
        ctx.receive_event(bot, e)

    assert task_info == {}


async def test_cron_list_and_delete_loop(app: App, isolated, monkeypatch):
    """循环提醒（Cron 与 Interval 各一）的列表与删除。"""
    _, task_info = isolated
    fixed_random(monkeypatch)
    members = [{"user_id": USER_ID, "card": "", "nickname": "小明"}]

    # 1) 关键词设置两条循环提醒
    e1 = group_event("每天8:00提醒我吃药", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e1, success_message(CronTrigger(hour=8, minute=0)))
        ctx.receive_event(bot, e1)

    e2 = group_event("每2小时提醒我喝水", to_me=True)
    async with app.test_matcher(plugin.remind_keyword) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e2, success_message(IntervalTrigger(hours=2)))
        ctx.receive_event(bot, e2)

    assert len(task_info) == 2

    # 2) 循环列表（按设置顺序：吃药、喝水）
    e3 = group_event("/循环提醒列表")
    async with app.test_matcher(plugin.list_cron_reminds) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_api(
            "get_group_member_list", {"group_id": GROUP_ID}, result=members
        )
        ctx.should_call_api(
            "get_group_member_list", {"group_id": GROUP_ID}, result=members
        )
        ctx.should_call_send(
            e3,
            Message(
                "您的循环提醒任务列表:\n"
                "01 时间: 每天08:00, 内容: [at 小明]吃药\n\n"
                "02 时间: 每隔 2 小时, 内容: [at 小明]喝水"
            ),
        )
        ctx.receive_event(bot, e3)

    # 3) 删除第二条（间隔任务）
    e4 = group_event("/删除循环提醒 2")
    async with app.test_matcher(plugin.del_cron_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_api(
            "get_group_member_list", {"group_id": GROUP_ID}, result=members
        )
        ctx.should_call_send(
            e4, Message("成功删除以下循环提醒任务！\n02  [at 小明]喝水")
        )
        ctx.receive_event(bot, e4)

    assert len(task_info) == 1
    remaining = next(iter(task_info.values()))
    assert remaining["type"] == "CronTrigger"


async def test_next_remind_reports_earliest(app: App, isolated, monkeypatch):
    """超级用户查询下次提醒：本插件任务、非本插件任务与无任务三分支。"""
    _, task_info = isolated
    task_info["t1"] = {"reminder_message": Message("开会")}
    run_at = datetime.now() + timedelta(hours=2)

    # 0) 有任务但全部处于暂停态（next_run_time 为 None）
    monkeypatch.setattr(
        scheduler,
        "get_jobs",
        lambda: [SimpleNamespace(id="x", next_run_time=None)],
    )
    e0 = fake_private_message_event_v11(message=Message("/下次提醒"))
    async with app.test_matcher(plugin.next_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e0, "已经没有定时任务啦！")
        ctx.receive_event(bot, e0)
        ctx.should_ignore_permission()

    # 1) 本插件的任务
    monkeypatch.setattr(
        scheduler, "get_jobs", lambda: [SimpleNamespace(id="t1", next_run_time=run_at)]
    )
    e1 = fake_private_message_event_v11(message=Message("/下次提醒"))
    async with app.test_matcher(plugin.next_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(
            e1,
            f"下次提醒时间：\n{colloquial_time(run_at)}\n提醒内容：\n"
            + Message("开会"),
        )
        ctx.receive_event(bot, e1)
        ctx.should_ignore_permission()

    # 2) 非本插件的任务
    monkeypatch.setattr(
        scheduler,
        "get_jobs",
        lambda: [SimpleNamespace(id="other", next_run_time=run_at)],
    )
    e2 = fake_private_message_event_v11(message=Message("/下次提醒"))
    async with app.test_matcher(plugin.next_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(
            e2,
            f"下次定时任务：\n{colloquial_time(run_at)}\n（不是由本插件提供的定时提醒服务）",
        )
        ctx.receive_event(bot, e2)
        ctx.should_ignore_permission()

    # 3) 没有任务
    monkeypatch.setattr(scheduler, "get_jobs", lambda: [])
    e3 = fake_private_message_event_v11(message=Message("/下次提醒"))
    async with app.test_matcher(plugin.next_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e3, "已经没有定时任务啦！")
        ctx.receive_event(bot, e3)
        ctx.should_ignore_permission()


def _noop() -> None:
    """供调度器持有的空任务函数（删除流程需要对应 job 存在）。"""


def _existing_task(task_id: str, *, kind: str = "datetime") -> dict:
    return {
        "task_id": task_id,
        "reminder_user_id": str(USER_ID),
        "user_ids": Message(MessageSegment.at(USER_ID)),
        "type": kind,
        "remind_time": datetime.now() + timedelta(hours=1),
        "reminder_message": Message("开会"),
        "is_group": True,
        "group_id": GROUP_ID,
    }


async def test_remind_empty_time_finishes(app: App, isolated):
    """参数首段为空（逗号开头）时提示时间不可为空。"""
    _, task_info = isolated

    e = group_event("/remind ,开会")
    async with app.test_matcher(plugin.remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e, "提醒时间不可为空！")
        ctx.receive_event(bot, e)
        ctx.should_finished()

    assert task_info == {}


async def test_remind_bad_segment_finishes(app: App, isolated):
    """参数含不支持的消息段时提示输入不正确。"""
    _, task_info = isolated

    face = MessageSegment.face(5)
    event = group_event(Message("/remind ") + face)
    async with app.test_matcher(plugin.remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(
            event, f"时间输入不正确！type={face.type},data={face.data}"
        )
        ctx.receive_event(bot, event)
        ctx.should_finished()

    assert task_info == {}


async def test_del_remind_empty_args_and_bad_format(app: App, isolated):
    """删除提醒：空参数与非法格式（多段连字符）的提示。"""
    _, task_info = isolated

    e1 = group_event("/删除提醒")
    async with app.test_matcher(plugin.del_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e1, "请提供要删除的任务序号。")
        ctx.receive_event(bot, e1)
        ctx.should_finished()

    e2 = group_event("/删除提醒 1-2-3")
    async with app.test_matcher(plugin.del_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e2, "参数不正确：序号应写成“1 3-6”这样的形式。")
        ctx.receive_event(bot, e2)


async def test_del_remind_all_flow_and_task_gone(app: App, isolated):
    """删除全部提醒；以及记录在但调度任务缺失时的业务异常提示。"""
    _, task_info = isolated
    members = [{"user_id": USER_ID, "card": "", "nickname": "小明"}]

    # 记录与调度任务都在：删除全部
    task_info["t1"] = _existing_task("t1")
    scheduler.add_job(
        _noop, "date", run_date=datetime.now() + timedelta(hours=1), id="t1"
    )
    e1 = group_event("/删除提醒 all")
    async with app.test_matcher(plugin.del_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_api(
            "get_group_member_list", {"group_id": GROUP_ID}, result=members
        )
        ctx.should_call_send(e1, Message("成功删除以下提醒任务！\n01  [at 小明]开会"))
        ctx.should_call_send(e1, "成功删除全部提醒！")
        ctx.receive_event(bot, e1)
        ctx.should_finished()
    assert task_info == {}

    # 记录在但调度任务缺失：业务异常提示，记录保留
    task_info["t2"] = _existing_task("t2")
    e2 = group_event("/删除提醒 1")
    async with app.test_matcher(plugin.del_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e2, "任务01不存在或已被删除。")
        ctx.receive_event(bot, e2)
    assert "t2" in task_info


async def test_del_cron_empty_all_and_task_gone(app: App, isolated):
    """循环删除：空参数；删除全部；以及任务缺失的业务异常提示。"""
    _, task_info = isolated
    members = [{"user_id": USER_ID, "card": "", "nickname": "小明"}]

    e0 = group_event("/删除循环提醒")
    async with app.test_matcher(plugin.del_cron_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e0, "请提供要删除的循环任务序号。")
        ctx.receive_event(bot, e0)
        ctx.should_finished()

    task_info["c1"] = _existing_task("c1", kind="CronTrigger")
    scheduler.add_job(
        _noop, "date", run_date=datetime.now() + timedelta(hours=1), id="c1"
    )
    e1 = group_event("/删除循环提醒 all")
    async with app.test_matcher(plugin.del_cron_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_api(
            "get_group_member_list", {"group_id": GROUP_ID}, result=members
        )
        ctx.should_call_send(
            e1, Message("成功删除以下循环提醒任务！\n01  [at 小明]开会")
        )
        ctx.should_call_send(e1, "成功删除全部循环提醒！")
        ctx.receive_event(bot, e1)
        ctx.should_finished()
    assert task_info == {}

    task_info["c2"] = _existing_task("c2", kind="CronTrigger")
    e2 = group_event("/删除循环提醒 1")
    async with app.test_matcher(plugin.del_cron_remind) as ctx:
        bot = make_bot(ctx)
        ctx.should_call_send(e2, "任务01不存在或已被删除。")
        ctx.receive_event(bot, e2)
    assert "c2" in task_info
