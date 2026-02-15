"""数据文件迁移模块。

在 load_tasks() 中调用，将旧版数据格式升级到当前版本。
"""

import re
from datetime import datetime

from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.log import logger


def migrate_task(task_id: str, task: dict) -> bool:
    """迁移单个任务的数据格式，返回是否发生了变更。"""
    changed = False

    # v0.1.3: 缺少 type 字段，remind_time 为字符串
    if "type" not in task:
        task["type"] = "datetime"
        task["remind_time"] = datetime.strptime(
            task["remind_time"], "%Y-%m-%d %H:%M:%S"
        )
        changed = True
        logger.debug(f"[迁移] 任务 {task_id}: 补充 type 字段")

    # v0.1.6: reminder_message 从 str 改为 Message
    if isinstance(task.get("reminder_message"), str):
        task["reminder_message"] = Message(task["reminder_message"])
        changed = True
        logger.debug(f"[迁移] 任务 {task_id}: reminder_message str → Message")

    # v0.1.10: user_ids 从 CQ 码字符串改为 Message
    if isinstance(task.get("user_ids"), str):
        task["user_ids"] = _cq_to_message(task["user_ids"])
        changed = True
        logger.debug(f"[迁移] 任务 {task_id}: user_ids CQ码 → Message")

    return changed


def migrate_all(task_info: dict) -> int:
    """迁移所有任务，返回变更数量。"""
    count = 0
    for task_id, task in task_info.items():
        if migrate_task(task_id, task):
            count += 1
    if count:
        logger.info(f"[迁移] 共迁移 {count} 个任务")
    return count


def _cq_to_message(cq_string: str) -> Message:
    """将 CQ 码字符串解析为 Message。

    "[CQ:at,qq=12345] [CQ:at,qq=all] " → Message([at(12345), at("all")])
    """
    msg = Message()
    for match in re.finditer(r"\[CQ:at,qq=(\w+)(?:,name=@?([^\]]*))?\]", cq_string):
        qq_val = match.group(1)
        if qq_val == "all":
            msg.append(MessageSegment.at("all"))
        else:
            msg.append(MessageSegment.at(int(qq_val)))
    return msg
