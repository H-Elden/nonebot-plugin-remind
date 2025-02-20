import re
import json
import jsonpickle
from nonebot.log import logger
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.triggers.cron import CronTrigger
from .common import task_info, TASKS_FILE
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
        f.write(jsonpickle.encode(task_info, indent=4))
    logger.info(f"提醒任务文件已保存到 {TASKS_FILE}")


def cq_to_at(s: str):
    """
    将CQ码中at的部分转换成纯文本
    """
    # 第一种情况：[CQ:at,qq=数字,name=文字]的模式
    pattern1 = r"\[CQ:at,qq=\d+,name=(.*?)\]"
    # 使用正则表达式替换匹配到的CQ码
    replaced_string = re.sub(pattern1, r"[at \1]", s)

    # 第二种情况：匹配at全体成员
    pattern2 = r"\[CQ:at,qq=all\]"
    replaced_string = re.sub(pattern2, r"[at 全体成员]", replaced_string)

    # 第三种情况：匹配at你（没有name=文字就说明是@发送者本人
    pattern2 = r"\[CQ:at,qq=\d+\]"
    replaced_string = re.sub(pattern2, r"[at 你]", replaced_string)

    return replaced_string


def colloquial_time(remind_time: datetime | CronTrigger) -> str:
    """
    将remind_time转换成口语化的时间表达。
    """
    if isinstance(remind_time, datetime):
        return colloquial_datetime(remind_time)
    elif isinstance(remind_time, CronTrigger):
        return colloquial_crontrigger(remind_time)
    else:
        raise TypeError("提醒时间类型不正确")


def colloquial_datetime(remind_time: datetime) -> str:
    """
    将datetime转换成口语化的时间表达。
    """
    if not isinstance(remind_time, datetime):
        return f"{remind_time}"
    now = datetime.now()
    cn_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = cn_days[remind_time.weekday()]
    diff_date = (remind_time.date() - now.date()).days
    diff_year = remind_time.year - now.year
    res = ""
    if diff_year == 0:
        if diff_date == 0:
            res += "今天"
        elif diff_date == 1:
            res += f"明天({weekday})"
        elif diff_date == 2:
            res += f"后天({weekday})"
        elif diff_date > 2:
            res += (
                f"{diff_date}天后({remind_time.month}月{remind_time.day}号 {weekday})"
            )
        else:
            # 如果diff_date是负数，说明提醒时间在现在之前
            res += f"{abs(diff_date)}天前({weekday})"
    elif diff_year == 1:
        res += f"明年{remind_time.month}月{remind_time.day}号({weekday})"
    elif diff_year == 2:
        res += f"后年{remind_time.month}月{remind_time.day}号({weekday})"
    else:
        res += (
            f"{remind_time.year}年{remind_time.month}月{remind_time.day}号({weekday})"
        )
    # 定义时间段的口语化表达
    time_periods = [
        (0, 5, "凌晨"),
        (5, 7, "清晨"),
        (7, 12, "上午"),
        (12, 13, "中午"),
        (13, 17, "下午"),
        (17, 19, "傍晚"),
        (19, 22, "晚上"),
        (22, 24, "夜里"),
    ]

    for start, end, period in time_periods:
        if start <= remind_time.hour < end:
            res += period
            break

    # 格式化时间，只显示小时和分钟，12小时制
    if remind_time.hour > 12:
        time_str = f"{remind_time.hour-12}点"
    else:
        time_str = f"{remind_time.hour}点"

    if remind_time.minute == 30:
        time_str += "半"
    elif remind_time.minute == 0:
        time_str += "整"
    else:
        time_str += f"{remind_time.minute}分"
    res += time_str

    return res


def colloquial_crontrigger(trigger: CronTrigger) -> str:
    return f"{str(trigger)[4:]}"


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


def get_user_tasks(user_id: str, group_id: Optional[int], sort: bool) -> list[dict]:
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


def get_user_cron_tasks(user_id: str, group_id: Optional[int]) -> list[dict]:
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
