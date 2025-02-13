import nonebot
from nonebot.adapters.onebot.v11 import (
    Message,
    GroupMessageEvent,
    Event,
    MessageEvent,
)
from nonebot import require, on_command, get_driver, on_keyword
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot.params import CommandArg, ArgStr
from nonebot.rule import to_me
from nonebot.log import logger

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

import os
import json
import random
from datetime import datetime, timedelta
from .config import Config, remind_config
from .common import time_format, task_info, TASKS_FILE
from .utils import (
    save_tasks_to_file,
    format_timedelta,
    parsed_time,
    get_user_tasks,
    cq_to_at,
)
from .data_sourse import send_reminder, set_reminder

__plugin_meta__ = PluginMetadata(
    name="定时提醒",
    description="符合中国宝宝体质的定时提醒功能~",
    usage=(
        "【命令匹配】\n"
        "/remind   设置定时提醒\n"
        "/提醒列表   查看当前所有定时任务：只能查看当前群聊定时的任务，私聊私聊可查看全部任务\n"
        '/删除提醒   删除定时任务，例如参数为"1 3-6"时表示删除任务ID为13456这些提醒任务。当参数为"all"时删除当前群全部定时任务。\n'
        "【关键词匹配】：提醒\n"
        "[@][时间]'提醒'[被提醒人][消息]\n"
        "例如“@机器人 22.35提醒我和@用户1 @用户2 去吃夜宵”\n"
        "可以用“all”或者“所有人”来代替 @全体成员 ，避免影响别人。\n"
        "\n支持的时间格式有：\n" + "\n".join(time_format)
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

# 创建命令处理器
remind = on_command("remind", aliases={"提醒"}, priority=5, block=True)
remind_keyword = on_keyword({"提醒"}, rule=to_me(), priority=6, block=True)
del_remind = on_command("dr", aliases={"删除提醒"}, priority=5, block=True)
list_reminds = on_command("lr", aliases={"提醒列表"}, priority=5, block=True)


# 在机器人启动时加载任务信息
@driver.on_startup
async def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            total_tasks = 0
            expired_tasks = 0
            current_time = datetime.now()
            global task_info
            for task_id, task_data in data.items():
                # 获取任务信息
                reminder_user_id = task_data["reminder_user_id"]
                remind_time = datetime.strptime(
                    task_data["remind_time"], "%Y-%m-%d %H:%M:%S"
                )
                user_ids = task_data["user_ids"]
                reminder_message = task_data["reminder_message"]
                is_group = task_data["is_group"]
                group_id = task_data["group_id"]
                # 检查定时任务是否过时
                if remind_time <= current_time:
                    # 过时任务数+1
                    expired_tasks += 1
                    # 30秒内发完所有过时信息的提示
                    n = random.randint(10, 30)
                    delay_time = current_time - remind_time + timedelta(seconds=n)
                    reminder_message += f'\n【十分抱歉，由于账号离线，此提醒任务已超时{format_timedelta(delay_time)}。原定提醒时间为：{remind_time.strftime("%Y-%m-%d %H:%M")}】'
                    remind_time = current_time + timedelta(seconds=n)
                else:
                    # 如果没有过时，总任务数+1
                    total_tasks += 1
                    # 没有超时才需要存储这些信息
                    task_info[task_id] = {
                        "task_id": task_id,
                        "reminder_user_id": reminder_user_id,
                        "user_ids": user_ids,
                        "remind_time": remind_time,
                        "reminder_message": reminder_message,
                        "is_group": is_group,
                        "group_id": group_id,
                    }

                # 恢复定时任务
                scheduler.add_job(
                    send_reminder,
                    "date",
                    run_date=remind_time,
                    args=[task_id, user_ids, reminder_message, is_group, group_id],
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


# 初始化状态
@remind.handle()
async def _(event: Event, state: T_State, args: Message = CommandArg()):
    user_ids = ""
    remind_time = None
    reminder_message = ""
    for msg in args:
        # 时间参数存入，则只需存提醒内容
        if remind_time:
            if msg.type == "text":
                reminder_message += msg.data["text"]
            else:
                cqmsg = f"[CQ:{msg.type}"
                for key, value in msg.data.items():
                    cqmsg += f",{key}={value}"
                cqmsg += "]"
                reminder_message += cqmsg
            continue
        # 没有传入时间参数，处理at，分割时间和提醒内容
        if msg.type == "at":
            atmsg = "[CQ:at"
            for key, value in msg.data.items():
                atmsg += f",{key}={value}"
            atmsg += "] "
            user_ids += atmsg
        elif msg.type == "text":
            # 忽略at后面紧跟的单空格
            if str(msg) == " ":
                continue
            # 处理第2，3个参数，随即break
            else:
                # 使用split()方法分割字符串
                # 限制分割次数为1，这样只会在第一个逗号处分割
                parts = str(msg).split(",", 1)
                # 获取第一个英文逗号之前的内容，并存储到变量a中
                a = parts[0] if parts else ""
                # 如果存在逗号之后的内容，则获取并存储到变量b中
                b = parts[1] if len(parts) > 1 else ""
                if a.strip() == "":
                    await remind.finish("提醒时间不可为空！")
                # 得到第2个参数：提醒时间
                remind_time = a.strip()
                # 组合得到第3个参数：提醒内容
                reminder_message += b
        else:
            await remind.finish(f"时间输入不正确！type={msg.type},data={msg.data}")
    if user_ids:
        state["user_ids"] = user_ids
    # 否则默认为命令发起者
    else:
        state["user_ids"] = f"[CQ:at,qq={event.get_user_id()}] "
    if remind_time:
        state["remind_time"] = remind_time
    if reminder_message:
        state["reminder_message"] = reminder_message


# 获取提醒时间
@remind.got("remind_time", prompt="提醒时间？推荐使用 HH.MM 或者 MM.DD.HH.MM 的格式。")
async def _(state: T_State, remind_time: str = ArgStr("remind_time")):
    if remind_time.strip().lower() in ["取消", "cancel"]:
        await remind.finish("已取消提醒设置。")
    final_time = await parsed_time(remind_time)
    if final_time is None:
        await remind.reject(
            "时间格式不正确。请重新输入或发送“取消”中止交互。\n仅支持以下格式：\n"
            + "\n".join(time_format)
        )
    state["remind_time"] = final_time


# 获取提醒信息
@remind.got("reminder_message", prompt="提醒信息？请输入您想要发送的信息。")
async def _(state: T_State, reminder_message: str = ArgStr("reminder_message")):
    if reminder_message.strip().lower() in ["取消", "cancel"]:
        await remind.finish("已取消提醒设置。")
    state["reminder_message"] = reminder_message


# 设置定时提醒
@remind.handle()
async def set_reminder_command(event: Event, state: T_State):
    """响应命令的提醒设置"""
    await set_reminder(event, state)


# 捕获“提醒”关键词
@remind_keyword.handle()
async def _(event: MessageEvent, state: T_State):
    """处理参数"""
    msg_list = event.message
    user_ids = ""
    remind_time = None
    remind_message = ""
    if msg_list[0].type == "text":
        keymsg = str(msg_list[0]).strip()
        if "提醒" in keymsg:
            # 使用split()方法分割字符串
            # 限制分割次数为1，这样只会在第一个"提醒"处分割
            parts = keymsg.split("提醒", 1)
            # 获取第一个"提醒"之前的内容，并存储到变量a中
            a = parts[0].strip() if parts else ""
            # 如果存在逗号之后的内容，则获取并存储到变量b中
            b = parts[1].strip() if len(parts) > 1 else ""

            # 保存时间参数
            remind_time = await parsed_time(a)
            if remind_time is None:
                state["success"] = False
                if remind_config.remind_keyword_error:
                    await remind_keyword.send("关键词【提醒】触发：未匹配到时间")
                return
            state["remind_time"] = remind_time

            # 处理用户参数
            if b == "我和" and len(msg_list) > 1 and msg_list[1].type == "at":
                # 12.20提醒我和@用户1 @用户2 去吃饭
                user_ids += f"[CQ:at,qq={event.get_user_id()}] "
            elif b == "" and len(msg_list) > 1 and msg_list[1].type == "at":
                # 12.20提醒@用户1 @用户2 去吃饭
                pass
            elif b.startswith("我"):
                # 12.20提醒我去吃饭
                user_ids += f"[CQ:at,qq={event.get_user_id()}] "
                remind_message += b[1:]  # 删掉"我"，保留"去吃饭"
            elif b.startswith("all") or b.startswith("所有人"):
                # 14.20提醒all去开会
                user_ids += f"[CQ:at,qq=all] "
                remind_message += b[3:]  # 删掉"all"或者"所有人"，保留"去开会"
            else:
                state["success"] = False
                if remind_config.remind_keyword_error:
                    await remind_keyword.send("关键词【提醒】触发：未匹配到提醒人")
                return

            for i in range(1, len(msg_list)):
                if remind_message:
                    # 剩下msg全部作为remind_message
                    if msg_list[i].type == "text":
                        remind_message += msg_list[i].data["text"]
                    else:
                        cqmsg = f"[CQ:{msg_list[i].type}"
                        for key, value in msg_list[i].data.items():
                            cqmsg += f",{key}={value}"
                        cqmsg += "]"
                        remind_message += cqmsg
                    continue
                # 还有需要at的用户
                if msg_list[i].type == "at":
                    atmsg = "[CQ:at"
                    for key, value in msg_list[i].data.items():
                        atmsg += f",{key}={value}"
                    atmsg += "] "
                    user_ids += atmsg
                elif msg_list[i].type == "text":
                    # 忽略at后面紧跟的单空格
                    if str(msg_list[i]) == " ":
                        continue
                    else:
                        # 组合得到第3个参数：提醒内容
                        remind_message += msg_list[i].data["text"]
            if user_ids and remind_message:
                state["user_ids"] = user_ids
                state["reminder_message"] = remind_message.strip()
                state["success"] = True
            else:
                state["success"] = False
                if remind_config.remind_keyword_error:
                    await remind_keyword.send("关键词【提醒】触发：未匹配到提醒信息")

        else:
            state["success"] = False
            if remind_config.remind_keyword_error:
                await remind_keyword.send("关键词【提醒】触发：“提醒”不在正确的位置")
    else:
        state["success"] = False
        if remind_config.remind_keyword_error:
            await remind_keyword.send("关键词【提醒】触发：消息应当以文本开头")


@remind_keyword.handle()
async def set_reminder_keyword(event: Event, state: T_State):
    """关键词捕获的提醒设置"""
    if state["success"] == True:
        await set_reminder(event, state)
    # else:
    #     await remind_keyword.finish("FALSE")


# 删除提醒任务
@del_remind.handle()
async def del_remind_handler(event: Event, args: Message = CommandArg()):
    reminder_user_id = event.get_user_id()
    group_id = event.group_id if isinstance(event, GroupMessageEvent) else None
    # 用户输入的任务ID
    id = args.extract_plain_text().strip()
    if not id:
        await del_remind.finish("请提供要删除的任务ID。")

    try:
        if id == "all":
            user_tasks = get_user_tasks(reminder_user_id, group_id, True)
            for task in user_tasks:
                task_id = task["task_id"]
                rmsg = task["reminder_message"]
                job = scheduler.get_job(task_id)
                if job:
                    job.remove()
                    msg = rmsg if len(rmsg) < 10 else rmsg[:20] + "..."
                    logger.success(f"成功删除提醒[{task_id}]:{repr(msg)}")
                    del task_info[task_id]
                else:
                    raise RuntimeError(f"任务[{task_id}]不存在或已被删除。")
            save_tasks_to_file()  # 更新任务信息到文件
            await del_remind.finish("成功删除全部提醒！")
        # 参数不是"all"的情况下
        sort = True
        indexes = []
        # 采用空白符分割参数
        ids = id.split()
        # 解析每个参数
        for idd in ids:
            if idd == "-s":
                # 采用设置时间排序的任务ID
                sort = False
                continue
            parts = idd.split("-")
            if len(parts) == 1:
                indexes.append(int(idd) - 1)
            elif len(parts) == 2:
                l_index = int(parts[0]) - 1
                r_index = int(parts[1]) - 1
                if l_index > r_index:
                    raise ValueError(f"{idd}为不正确的参数。")
                indexes.extend(range(l_index, r_index + 1))
            else:
                raise ValueError(f'"{idd}"为不正确的参数格式。')
        # 给列表去重
        indexes = list(set(indexes))
        # 获取用户任务列表
        user_tasks = get_user_tasks(reminder_user_id, group_id, sort)

        msg_list = []
        for index in indexes:
            if index < 0 or index >= len(user_tasks):
                raise ValueError("任务ID超出范围")
            task_id = user_tasks[index]["task_id"]
            job = scheduler.get_job(task_id)
            msg = cq_to_at(
                user_tasks[index]["user_ids"] + user_tasks[index]["reminder_message"]
            )
            if job:
                job.remove()
                info = (
                    user_tasks[index]["reminder_message"]
                    if len(user_tasks[index]["reminder_message"]) < 10
                    else user_tasks[index]["reminder_message"][:20] + "..."
                )
                logger.success(f"成功删除提醒[{task_id}]:{repr(info)}")
                del task_info[task_id]
                msg_list.append(f"{index+1:02d}  {msg}")
            else:
                raise RuntimeError(f"任务{index+1:02d}不存在或已被删除。")
        msgs = "\n\n".join(msg_list)
        await del_remind.send(Message("成功删除以下提醒任务！\n" + msgs))
        save_tasks_to_file()  # 更新任务信息到文件
    except ValueError as e:
        await del_remind.send(f'任务ID"{id}"参数错误：{e}')
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
            reminder_message = task["reminder_message"]
            # 将其中的at改为纯文本，避免打扰别人
            msg += cq_to_at(user_ids + reminder_message)
            msg_list.append(msg)
        msgs = "\n\n".join(msg_list)
        await list_reminds.send(Message("您的提醒任务列表:\n" + msgs))
    else:
        await list_reminds.send("您目前没有设置任何提醒任务。")
