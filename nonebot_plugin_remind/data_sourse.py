import nonebot
from nonebot.adapters.onebot.v11 import (
    Message,
    GroupMessageEvent,
    MessageSegment,
    Event,
)
from nonebot_plugin_apscheduler import scheduler
from datetime import datetime, timedelta
from nonebot.typing import T_State
from nonebot.log import logger
import random

from .common import task_info
from .utils import save_tasks_to_file, colloquial_time


# 设置定时提醒
async def set_reminder(event: Event, state: T_State):
    user_ids = state["user_ids"]  # 被提醒人的id列表，元素类型为str
    remind_time = state["remind_time"]
    reminder_message = state["reminder_message"]

    bot = nonebot.get_bot()
    # 当前时间
    now = datetime.now()

    # 计算延迟时间
    delay = (remind_time - now).total_seconds()
    if delay <= 0:
        await bot.send(event, "提醒时间已过，请设置未来的时间。")
        return

    # 给提醒时间加上随机秒数，防止同一秒发送过多消息被tx检测到
    remind_time += timedelta(seconds=random.randint(0, 30))

    # 判断是私聊还是群聊
    is_group = isinstance(event, GroupMessageEvent)
    group_id = event.group_id if is_group else int(event.get_user_id())

    # 添加定时任务
    job = scheduler.add_job(
        send_reminder,
        "date",
        run_date=remind_time,
        args=[
            None,
            user_ids,
            reminder_message,
            is_group,
            group_id,
        ],  # 先将None作为任务ID传入
    )

    # 记录任务信息
    task_id = job.id
    # 更新定时任务参数，将任务ID传递进去
    job.modify(args=[task_id, user_ids, reminder_message, is_group, group_id])
    logger.success(f'成功设置提醒任务:{remind_time.strftime("%Y-%m-%d %H:%M:%S")}')

    # 获取任务发起者（提醒人）的ID
    reminder_user_id = event.get_user_id()
    task_info[task_id] = {
        "task_id": task_id,  # str
        "reminder_user_id": reminder_user_id,  # str
        "user_ids": user_ids,  # str
        "remind_time": remind_time,  # datetime
        "reminder_message": reminder_message,  # str
        "is_group": is_group,  # bool
        "group_id": group_id,  # int
    }

    # 构建消息
    face_id = [314, 175, 183, 307, 355, 298, 293, 285]
    success_msg = [
        "好的！",
        "没问题！",
        "你就放心交给我吧！",
        "收到！",
        "包在我身上！",
        "看我的吧！",
        "有我在，你放一百万个心好了！",
    ]
    # 组合"成功消息"和"表情"
    msg = Message(
        MessageSegment.text(random.choice(success_msg))
        + MessageSegment.face(random.choice(face_id))
    )
    # 计数，at几个人
    id_num = user_ids.count("at")
    pron = ""
    if "all" in user_ids:
        pron = "你们"
    elif event.get_user_id() in user_ids:
        pron = "你们" if id_num > 1 else "你"
    else:
        pron = "他们" if id_num > 1 else "他"

    msg += MessageSegment.text(
        f"我会在{colloquial_time(remind_time)}准时提醒{pron}的！"
    )
    await bot.send(event, msg)

    # 保存任务信息到文件
    save_tasks_to_file()


# 定义定时提醒函数
async def send_reminder(
    task_id: str,
    user_ids: str,
    reminder_message: str,
    is_group: bool = False,
    group_id: int = None,
):
    bot = nonebot.get_bot()
    if is_group:
        message = Message(user_ids + reminder_message)
        await bot.send_group_msg(group_id=group_id, message=message)
    else:
        # 发送提醒信息到私聊，私聊时group_id即为用户qq号
        await bot.send_private_msg(user_id=group_id, message=Message(reminder_message))

    # 任务完成后从任务信息中移除
    if task_id in task_info:
        del task_info[task_id]
        msg = (
            reminder_message
            if len(reminder_message) < 10
            else reminder_message[:20] + "..."
        )
        logger.success(f"成功发送提醒[{task_id}]:{repr(msg)}")
        save_tasks_to_file()  # 更新任务信息到文件
