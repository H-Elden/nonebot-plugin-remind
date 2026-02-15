from __future__ import annotations

import json
from datetime import timedelta

import jsonpickle
from nonebot.adapters.onebot.v11 import Message
from nonebot.log import logger

from .common import TASKS_FILE, task_info
from .config import remind_config


# 自定义 JSON 编码器
class CustomJSONEncoder(json.JSONEncoder):
    def __init__(self, **kwargs):
        kwargs["ensure_ascii"] = False
        super().__init__(**kwargs)


# 设置 jsonpickle 使用自定义编码器
jsonpickle.set_encoder_options("json", cls=CustomJSONEncoder)


def save_tasks_to_file():
    """
    将当前提醒任务保存到本地文件
    """
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        f.write(str(jsonpickle.encode(task_info, indent=4)))
    logger.info(f"提醒任务文件已保存到 {TASKS_FILE}")


def at_to_text(user_ids: Message) -> str:
    """将 at 消息段转换为纯文本，用于展示（避免打扰被 at 的人）。

    MessageSegment.at(12345) → "[at 你]"
    MessageSegment.at("all") → "[at 全体成员]"
    如有 name 字段则使用 name。
    """
    parts = []
    for seg in user_ids:
        if seg.type == "at":
            qq = seg.data.get("qq")
            name = seg.data.get("name", "").lstrip("@")
            if str(qq) == "all":
                parts.append("[at 全体成员]")
            elif name:
                parts.append(f"[at {name}]")
            else:
                parts.append("[at 你]")
        else:
            parts.append(str(seg))
    return "".join(parts)


def format_timedelta(td: timedelta):
    def add_unit(value, unit, result: list):
        if value:
            result.append(f"{value}{unit}")
        return result

    days, seconds = td.days, td.seconds
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    add_unit(days, "天", parts)
    add_unit(hours, "小时", parts)
    add_unit(minutes, "分钟", parts)

    return "".join(parts) or f"{int(td.total_seconds())}秒"


def get_user_tasks(user_id: str, group_id: int | None, sort: bool) -> list[dict]:
    """从全局变量task_info获取用户的单次提醒任务

    参数：
        user_id:str 提醒人用户id
        group_id:int 群聊id, 私聊为None
        sort:bool 是否采用排序后的id
    返回：
        任务列表
    """
    # 私聊列出所有提醒
    if remind_config.private_list_all:
        user_tasks = [
            task
            for task in task_info.values()
            if task["reminder_user_id"] == user_id
            and task["type"] == "datetime"
            and (group_id is None or task["group_id"] == group_id)
        ]
    # 私聊仅列出私聊提醒
    else:
        user_tasks = [
            task
            for task in task_info.values()
            if task["reminder_user_id"] == user_id
            and task["type"] == "datetime"
            and (
                (group_id is None and task["group_id"] == int(user_id))
                or task["group_id"] == group_id
            )
        ]
    if sort:
        user_tasks.sort(key=lambda x: x["remind_time"])
    return user_tasks


def get_user_cron_tasks(user_id: str, group_id: int | None) -> list[dict]:
    """从全局变量task_info获取用户的循环提醒任务

    参数：
        user_id:str 提醒人用户id
        group_id:int 群聊id, 私聊为None
    返回：
        任务列表
    """
    # 私聊列出所有提醒
    if remind_config.private_list_all:
        user_tasks = [
            task
            for task in task_info.values()
            if task["reminder_user_id"] == user_id
            and task["type"] == "CronTrigger"
            and (group_id is None or task["group_id"] == group_id)
        ]
    # 私聊仅列出私聊提醒
    else:
        user_tasks = [
            task
            for task in task_info.values()
            if task["reminder_user_id"] == user_id
            and task["type"] == "CronTrigger"
            and (
                (group_id is None and task["group_id"] == int(user_id))
                or task["group_id"] == group_id
            )
        ]
    return user_tasks
