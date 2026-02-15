from nonebot import get_driver, on_command, on_keyword, require
from nonebot.adapters.onebot.v11 import (
    Event,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.exception import FinishedException
from nonebot.log import logger
from nonebot.params import ArgStr, CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule, to_me
from nonebot.typing import T_State

require("nonebot_plugin_apscheduler")

import os
import random
from datetime import datetime, timedelta

import jsonpickle
from nonebot_plugin_apscheduler import scheduler

from .colloquial import colloquial_time
from .common import TASKS_FILE, task_info
from .config import Config, remind_config
from .data_sourse import send_reminder, set_reminder
from .migration import migrate_all
from .parse import extract_time_and_message, parse_time
from .utils import (
    at_to_text,
    format_timedelta,
    get_user_cron_tasks,
    get_user_tasks,
    save_tasks_to_file,
)

__plugin_meta__ = PluginMetadata(
    name="定时提醒",
    description="符合中国宝宝体质的定时提醒功能~",
    usage=(
        "【命令匹配】\n"
        "/remind   设置定时提醒\n"
        "/提醒列表   查看当前所有单次定时任务：只能查看当前群聊定时的任务，私聊可查看全部任务\n"
        '/删除提醒   删除单次定时任务，例如参数为"1 3-6"时表示删除任务ID为13456这些提醒任务。当参数为"all"时删除当前群全部定时任务。\n'
        "/循环提醒列表   查看当前所有循环定时任务，同上\n"
        "/删除循环提醒   删除循环定时任务，同上\n"
        "【关键词匹配】：提醒\n"
        "[@][时间]'提醒'[被提醒人][消息]\n"
        "例如“@机器人 22.35提醒我和@用户1 @用户2 去吃夜宵”可设置单次提醒\n"
        "例如“@机器人 每天8:00提醒我早安~”可设置循环提醒\n"
        "可以用“all”或者“所有人”来代替 @全体成员 ，避免影响别人。\n"
        "\n支持多种时间格式，包括但不限于：\n"
        "  14:30、2026-3-15 9:00\n"
        "  明天下午3点、后天上午10点、下周一9点\n"
        "  半小时后、10分钟后、两个小时后\n"
        "  春节、国庆节、中秋节\n"
        "  每天13:30、每周三14:00、每月15号9:30"
    ),
    type="application",
    homepage="https://github.com/H-Elden/nonebot-plugin-remind",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

# 获取驱动器实例
driver = get_driver()

# 检查 scheduler 是否初始化
if scheduler is None:
    raise RuntimeError(
        "Scheduler not initialized. Please check your plugin configuration."
    )


def private_checker():
    """是否为私聊发送消息"""

    async def _checker(event: Event) -> bool:
        return isinstance(event, PrivateMessageEvent)

    return Rule(_checker)


# 创建命令处理器
remind = on_command("remind", aliases={"提醒"}, priority=5, block=True)
remind_keyword = on_keyword({"提醒"}, rule=to_me(), priority=6, block=True)
del_remind = on_command(
    "dr", aliases={"删除提醒", "删除单次提醒"}, priority=5, block=True
)
list_reminds = on_command(
    "lr", aliases={"提醒列表", "单次提醒列表"}, priority=5, block=True
)
del_cron_remind = on_command("drc", aliases={"删除循环提醒"}, priority=5, block=True)
list_cron_reminds = on_command("lrc", aliases={"循环提醒列表"}, priority=5, block=True)
next_remind = on_command(
    "next_remind",
    aliases={"nr", "下次提醒"},
    rule=private_checker(),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@next_remind.handle()
async def _():
    try:
        jobs = scheduler.get_jobs()

        if not jobs:
            await next_remind.finish("已经没有定时任务啦！")
        # 过滤掉没有next_run_time的作业（例如已暂停的作业）
        valid_jobs = [job for job in jobs if job.next_run_time is not None]
        if not valid_jobs:
            await next_remind.finish("已经没有定时任务啦！")

        # 按next_run_time排序，找到最早的执行时间
        next_job = min(valid_jobs, key=lambda job: job.next_run_time)
        if next_job.id in task_info.keys():
            msg = task_info[next_job.id]["reminder_message"]
            await next_remind.send(
                f"下次提醒时间：\n{colloquial_time(next_job.next_run_time)}\n提醒内容：\n"
                + msg
            )
        else:
            await next_remind.send(
                f"下次定时任务：\n{colloquial_time(next_job.next_run_time)}\n（不是由本插件提供的定时提醒服务）"
            )
    except FinishedException:
        pass
    except Exception as e:
        logger.error(e)
        await next_remind.send(f"{type(e).__name__}: {e}")


# 在机器人启动时加载任务信息
@driver.on_startup
async def load_tasks():
    if os.path.exists(TASKS_FILE):  # noqa: ASYNC240
        global task_info
        with open(TASKS_FILE, encoding="utf-8") as f:  # noqa: ASYNC230
            # 直接使用=赋值是不对的，会创建一个新的局部变量而不是修改全局变量
            task_info.clear()
            decoded = jsonpickle.decode(f.read())
            if isinstance(decoded, dict):
                task_info.update(decoded)
        total_tasks = 0
        expired_tasks = 0
        current_time = datetime.now()
        # 迁移旧版数据格式
        if migrate_all(task_info):
            save_tasks_to_file()
        for task_id in task_info:
            # 检查定时任务是否过时
            if (
                task_info[task_id]["type"] == "datetime"
                and task_info[task_id]["remind_time"] <= current_time
            ):
                # 过时任务数+1
                expired_tasks += 1
                # 30秒内发完所有过时信息的提示
                n = random.randint(10, 30)
                delay_time = (
                    current_time
                    - task_info[task_id]["remind_time"]
                    + timedelta(seconds=n)
                )
                task_info[task_id]["reminder_message"] += (
                    f"\n【十分抱歉，由于账号离线，此提醒任务已超时{format_timedelta(delay_time)}。原定提醒时间为：{task_info[task_id]['remind_time'].strftime('%Y-%m-%d %H:%M')}】"
                )
                task_info[task_id]["remind_time"] = current_time + timedelta(seconds=n)
            else:
                # 如果没有过时，总任务数+1
                total_tasks += 1
            # 恢复定时任务
            if task_info[task_id]["type"] == "datetime":
                scheduler.add_job(
                    send_reminder,
                    "date",
                    run_date=task_info[task_id]["remind_time"],
                    args=[
                        task_id,
                        task_info[task_id]["user_ids"],
                        task_info[task_id]["reminder_message"],
                        task_info[task_id]["is_group"],
                        task_info[task_id]["group_id"],
                    ],
                    id=task_id,
                )
            else:
                scheduler.add_job(
                    send_reminder,
                    trigger=task_info[task_id]["remind_time"],
                    args=[
                        task_id,
                        task_info[task_id]["user_ids"],
                        task_info[task_id]["reminder_message"],
                        task_info[task_id]["is_group"],
                        task_info[task_id]["group_id"],
                    ],
                    id=task_id,
                )

        # 输出信息
        if expired_tasks:
            info = f"已载入 {total_tasks} 个任务，删除 {expired_tasks} 个过时任务"
            logger.warning(info)
        else:
            info = f"全部 {total_tasks} 个定时任务均已载入完成！"
            logger.success(info)
        save_tasks_to_file()


# ── 辅助函数 ────────────────────────────────────────────────


def _extract_person(
    text: str, event: MessageEvent, msg_list: Message
) -> tuple[Message, str, bool]:
    """从文本开头提取人称目标。

    Returns:
        (user_ids, remaining_text, matched)
    """
    user_ids = Message()
    if text.startswith("我和") and len(msg_list) > 1 and msg_list[1].type == "at":
        user_ids += MessageSegment.at(event.get_user_id())
        return user_ids, text[2:], True
    if text == "" and len(msg_list) > 1 and msg_list[1].type == "at":
        return user_ids, text, True
    if text.startswith("我"):
        user_ids += MessageSegment.at(event.get_user_id())
        return user_ids, text[1:], True
    if text.startswith("all"):
        user_ids += MessageSegment.at("all")
        return user_ids, text[3:], True
    if text.startswith("所有人"):
        user_ids += MessageSegment.at("all")
        return user_ids, text[3:], True
    return user_ids, text, False


def _parse_task_indexes(
    raw_ids: str, *, allow_sort_flag: bool = False
) -> tuple[list[int], bool]:
    """解析用户输入的任务ID参数，返回 (索引列表, 是否按提醒时间排序)。

    支持格式: "1 3-6"  "1 2 -s"
    索引从0开始（用户输入从1开始）。
    """
    sort = True
    indexes: list[int] = []
    for part in raw_ids.split():
        if allow_sort_flag and part == "-s":
            sort = False
            continue
        segments = part.split("-")
        if len(segments) == 1:
            indexes.append(int(part) - 1)
        elif len(segments) == 2:
            lo, hi = int(segments[0]) - 1, int(segments[1]) - 1
            if lo > hi:
                raise ValueError(f"{part}为不正确的参数。")
            indexes.extend(range(lo, hi + 1))
        else:
            raise ValueError(f'"{part}"为不正确的参数格式。')
    return list(set(indexes)), sort


async def _delete_tasks(
    matcher,  # type: ignore[no-untyped-def]
    user_tasks: list[dict],
    indexes: list[int],
    *,
    label: str = "提醒",
) -> None:
    """按索引删除任务列表中的任务并发送结果消息。"""
    msg_list = []
    for index in indexes:
        if index < 0 or index >= len(user_tasks):
            raise ValueError("任务ID超出范围")
        tid = user_tasks[index]["task_id"]
        str_msg = str(user_tasks[index]["reminder_message"])
        group_id_temp = user_tasks[index]["group_id"] if user_tasks[index]["is_group"] else None
        job = scheduler.get_job(tid)
        if job:
            job.remove()
            info = str_msg if len(str_msg) <= 20 else str_msg[:20] + "..."
            logger.success(f"成功删除{label}[{tid}]:{info!r}")
            del task_info[tid]
            display = await at_to_text(group_id_temp, user_tasks[index]["user_ids"]) + str_msg
            msg_list.append(f"{index + 1:02d}  {display}")
        else:
            raise RuntimeError(f"任务{index + 1:02d}不存在或已被删除。")
    msgs = "\n\n".join(msg_list)
    try:
        await matcher.send(Message(f"成功删除以下{label}任务！\n" + msgs))
    except Exception:
        await matcher.send(f"成功删除以下{label}任务！(raw)\n" + msgs)
    save_tasks_to_file()


# ── /remind 命令交互 ─────────────────────────────────────────


@remind.handle()
async def _(event: Event, state: T_State, args: Message = CommandArg()):
    """解析 /remind 命令参数: @用户 时间,消息"""
    user_ids = Message()
    remind_time = None
    reminder_message = Message()
    for msg in args:
        if remind_time:
            reminder_message += msg
            continue
        if msg.type == "at":
            user_ids += MessageSegment.at(msg.data["qq"])
        elif msg.type == "text":
            if str(msg) == " ":
                continue
            text = str(msg)
            parts = text.split(",", 1) if "," in text else text.split("，", 1)
            a = parts[0] if parts else ""
            b = parts[1] if len(parts) > 1 else ""
            if a.strip() == "":
                await remind.finish("提醒时间不可为空！")
            remind_time = a.strip()
            reminder_message += b
        else:
            await remind.finish(f"时间输入不正确！type={msg.type},data={msg.data}")
    if user_ids:
        state["user_ids"] = user_ids
    else:
        state["user_ids"] = Message(MessageSegment.at(event.get_user_id()))
    if remind_time:
        state["remind_time"] = remind_time
    if reminder_message:
        state["reminder_message"] = reminder_message


# 获取提醒时间
@remind.got(
    "remind_time", prompt='提醒时间？支持自然语言，如"明天下午3点"、"每天8:00"。'
)
async def _(state: T_State, remind_time: str = ArgStr("remind_time")):
    if remind_time.strip().lower() in ["取消", "cancel"]:
        await remind.finish("已取消提醒设置。")
    final_time = await parse_time(remind_time)
    logger.debug(f"解析提醒时间结果为：{remind_time}")
    if final_time is None:
        await remind.reject(
            "时间格式不正确。请重新输入或发送“取消”中止交互。\n可尝试以下格式：\n"
            "支持格式如：14:30、明天下午3点、半小时后、每天8:00 等"
        )
    state["remind_time"] = final_time


# 获取提醒信息
@remind.got("reminder_message", prompt="提醒信息？请输入您想要发送的信息。")
async def _(state: T_State, reminder_message: str = ArgStr("reminder_message")):
    if reminder_message.strip().lower() in ["取消", "cancel"]:
        await remind.finish("已取消提醒设置。")
    state["reminder_message"] = Message(reminder_message)


# 设置定时提醒
@remind.handle()
async def set_reminder_command(event: Event, state: T_State):
    """响应命令的提醒设置"""
    await set_reminder(event, state)


# ── 关键词「提醒」交互 ────────────────────────────────────────


@remind_keyword.handle()
async def _(event: MessageEvent, state: T_State):
    """解析含“提醒”关键词的自然语言消息。"""
    msg_list = event.message
    user_ids = Message()
    remind_message = Message()

    if msg_list[0].type != "text":
        state["success"] = False
        if remind_config.remind_keyword_error:
            await remind_keyword.send("关键词【提醒】触发：消息应当以文本开头")
        return

    keymsg = str(msg_list[0]).strip()
    if "提醒" not in keymsg:
        state["success"] = False
        if remind_config.remind_keyword_error:
            await remind_keyword.send("关键词【提醒】触发：“提醒”不在正确的位置")
        return

    parts = keymsg.split("提醒", 1)
    before = parts[0].strip()
    after = parts[1].strip() if len(parts) > 1 else ""

    # ── 模式1: 时间+提醒+人+消息（例: "明天提醒我打胶"）──
    remind_time = await parse_time(before) if before else None
    logger.debug(f"模式1 解析提醒时间结果为：{remind_time}")

    if remind_time is not None:
        state["remind_time"] = remind_time
        person_ids, remaining, matched = _extract_person(after, event, msg_list)
        if not matched:
            state["success"] = False
            if remind_config.remind_keyword_error:
                await remind_keyword.send("关键词【提醒】触发：未匹配到提醒人")
            return
        user_ids += person_ids
        if remaining:
            remind_message += remaining
    else:
        # ── 模式2: 提醒+人+时间+消息（例: "提醒我明天打胶"）──
        person_ids, remaining, matched = _extract_person(after, event, msg_list)
        if not matched:
            state["success"] = False
            if remind_config.remind_keyword_error:
                await remind_keyword.send("关键词【提醒】触发：未匹配到提醒人")
            return
        user_ids += person_ids

        remaining = remaining.strip()
        if not remaining:
            state["success"] = False
            if remind_config.remind_keyword_error:
                await remind_keyword.send("关键词【提醒】触发：未匹配到时间")
            return

        parsed_time, msg_after_time = await extract_time_and_message(remaining)
        if parsed_time is None:
            state["success"] = False
            if remind_config.remind_keyword_error:
                await remind_keyword.send("关键词【提醒】触发：未匹配到时间")
            return
        state["remind_time"] = parsed_time
        if msg_after_time:
            remind_message += msg_after_time

    # 处理后续消息段（at 和文本/图片等）
    if remind_message:
        remind_message += msg_list[1:]
    else:
        for i in range(1, len(msg_list)):
            if msg_list[i].type == "at":
                user_ids += MessageSegment.at(msg_list[i].data["qq"])
            elif msg_list[i].type == "text" and str(msg_list[i]) == " ":
                continue
            else:
                remind_message += msg_list[i:]
                break

    if user_ids and remind_message:
        state["user_ids"] = user_ids
        state["reminder_message"] = remind_message
        state["success"] = True
    else:
        state["success"] = False
        if remind_config.remind_keyword_error:
            await remind_keyword.send("关键词【提醒】触发：未匹配到提醒信息")


@remind_keyword.handle()
async def set_reminder_keyword(event: Event, state: T_State):
    """关键词捕获的提醒设置"""
    if state["success"]:
        await set_reminder(event, state)


# ── 删除/列出任务 ─────────────────────────────────────────


@del_remind.handle()
async def del_remind_handler(event: Event, args: Message = CommandArg()):
    reminder_user_id = event.get_user_id()
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else None
    raw = args.extract_plain_text().strip()
    if not raw:
        await del_remind.finish("请提供要删除的任务ID。")

    try:
        if raw == "all":
            user_tasks = get_user_tasks(reminder_user_id, group_id, True)
            indexes = list(range(len(user_tasks)))
            await _delete_tasks(del_remind, user_tasks, indexes, label="提醒")
            await del_remind.finish("成功删除全部提醒！")

        indexes, sort = _parse_task_indexes(raw, allow_sort_flag=True)
        user_tasks = get_user_tasks(reminder_user_id, group_id, sort)
        await _delete_tasks(del_remind, user_tasks, indexes, label="提醒")
    except ValueError as e:
        await del_remind.send(f'任务ID"{raw}"参数错误：{e}')
    except RuntimeError as e:
        await del_remind.send(f"运行时错误：{e}")


# 列出用户的提醒任务
@list_reminds.handle()
async def list_reminds_handler(event: Event, args: Message = CommandArg()):
    reminder_user_id = event.get_user_id()
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else None
    # 可选参数"-s"，表示使用设置时间顺序输出。否则默认用提醒时间顺序输出
    arg = args.extract_plain_text().lower().strip()
    user_tasks = get_user_tasks(reminder_user_id, group_id, arg != "-s")

    if user_tasks:
        msg_list = []
        for index, task in enumerate(user_tasks, start=1):
            remind_time = task["remind_time"].strftime("%Y/%m/%d %H:%M")
            msg = f"{index:02d} 时间: {remind_time}, 内容: "
            user_ids = task["user_ids"]
            reminder_message = str(task["reminder_message"])
            # 将其中的at改为纯文本，避免打扰别人
            group_id_temp = task["group_id"] if task["is_group"] else None
            msg += await at_to_text(group_id_temp, user_ids) + reminder_message
            msg_list.append(msg)
        msgs = "\n\n".join(msg_list)
        try:
            await list_reminds.send(Message("您的提醒任务列表:\n" + msgs))
        except Exception:
            await list_reminds.send("您的提醒任务列表(raw):\n" + msgs)
    else:
        await list_reminds.send("您目前没有设置任何提醒任务。")


@del_cron_remind.handle()
async def del_cron_remind_handler(event: Event, args: Message = CommandArg()):
    reminder_user_id = event.get_user_id()
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else None
    raw = args.extract_plain_text().strip()
    if not raw:
        await del_cron_remind.finish("请提供要删除的循环任务ID。")

    try:
        if raw == "all":
            user_tasks = get_user_cron_tasks(reminder_user_id, group_id)
            indexes = list(range(len(user_tasks)))
            await _delete_tasks(del_cron_remind, user_tasks, indexes, label="循环提醒")
            await del_cron_remind.finish("成功删除全部循环提醒！")

        indexes, _ = _parse_task_indexes(raw)
        user_tasks = get_user_cron_tasks(reminder_user_id, group_id)
        await _delete_tasks(del_cron_remind, user_tasks, indexes, label="循环提醒")
    except ValueError as e:
        await del_cron_remind.send(f'任务ID"{raw}"参数错误：{e}')
    except RuntimeError as e:
        await del_cron_remind.send(f"运行时错误：{e}")


# 列出用户的循环提醒任务
@list_cron_reminds.handle()
async def list_cron_reminds_handler(event: Event):
    reminder_user_id = event.get_user_id()
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else None
    user_tasks = get_user_cron_tasks(reminder_user_id, group_id)

    if user_tasks:
        msg_list = []
        for index, task in enumerate(user_tasks, start=1):
            remind_time = task["remind_time"]
            msg = f"{index:02d} 时间: {colloquial_time(remind_time)}, 内容: "
            user_ids = task["user_ids"]
            reminder_message = str(task["reminder_message"])
            # 将其中的at改为纯文本，避免打扰别人
            group_id_temp = task["group_id"] if task["is_group"] else None
            msg += await at_to_text(group_id_temp, user_ids) + reminder_message
            msg_list.append(msg)
        msgs = "\n\n".join(msg_list)
        try:
            await list_cron_reminds.send(Message("您的循环提醒任务列表:\n" + msgs))
        except Exception:
            await list_cron_reminds.send("您的循环提醒任务列表(raw):\n" + msgs)
    else:
        await list_cron_reminds.send("您目前没有设置任何循环提醒任务。")
