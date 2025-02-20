import re
import ast
from datetime import datetime, timedelta
from apscheduler.triggers.cron import CronTrigger
from .glm4 import parsed_datetime_glm4, parsed_cron_time_glm4
from .common import time_format

from nonebot.log import logger


# 月份与最大天数字典（不考虑闰年精确计算）
MONTH_MAX_DAYS = {
    1: 31,
    2: 29,  # 允许闰日（实际校验时会接受2月29日）
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}


async def parse_time(remind_time: str) -> datetime | CronTrigger | None:
    try:
        # 把循环提醒时间解析为CronTrigger
        if remind_time.startswith("每"):
            return await parse_cron_trigger(remind_time)
        # 把单次提醒时间解析为datetime
        else:
            return await parse_date_trigger(remind_time)
    except ValueError as e:
        logger.error(e)
        return None


async def parse_date_trigger(time: str) -> datetime | None:
    """将提醒时间str解析为datetime"""
    logger.info(f'解析单次提醒时间:"{time}"')
    now = datetime.now()
    final_time = None

    # 将可能的分隔符 " ", "-", ":", "：" 替换为 "."
    result_string = (
        time.replace(" ", ".").replace("-", ".").replace(":", ".").replace("：", ".")
    )

    # 尝试解析不同格式的时间
    for fmt in time_format:
        try:
            final_time = datetime.strptime(result_string, fmt)
            break
        except ValueError:
            continue

    if final_time:
        # 调整时间格式
        if fmt == "%m.%d.%H.%M":
            final_time = final_time.replace(year=now.year)
            if final_time <= now:
                final_time = final_time.replace(year=now.year + 1)
        elif fmt == "%H.%M":
            final_time = final_time.replace(year=now.year, month=now.month, day=now.day)
            # 找到距离当前时间最近的未来的这个时间点，也就是如果今天已经过了这个时间点，就定时到明天
            if final_time <= now:
                final_time += timedelta(days=1)

    # 使用GLM-4的大语言模型解析时间
    else:
        res = await parsed_datetime_glm4(time)
        if res != "None" and res != "Error":
            final_time = datetime.strptime(res, "%Y-%m-%d %H:%M")

    return final_time


def validate_date_params(params: dict):
    """验证月份和日期的组合有效性"""
    if "month" in params and "day" in params:
        month = params["month"]
        day = params["day"]
        if day > MONTH_MAX_DAYS.get(month, 31):
            raise ValueError(f"无效的日期：{month}月没有{day}日")


async def parse_cron_trigger(time: str) -> CronTrigger:
    logger.info(f'解析循环提醒时间:"{time}"')
    # 正则匹配可能的时间表述
    patterns = [
        (r"每个?小?时的?(\d{1,2})分?", ["minute"]),
        (r"每天的?(\d{1,2})[：:.点](\d{1,2})分?", ["hour", "minute"]),
        (
            r"每个?月的?(\d{1,2})[号日.]的?(\d{1,2})[：:.点](\d{1,2})分?",
            ["day", "hour", "minute"],
        ),
        (
            r"每个?年的?(\d{1,2})[月.](\d{1,2})[号日.]的?(\d{1,2})[：:.点](\d{1,2})分?",
            ["month", "day", "hour", "minute"],
        ),
        (
            r"每个?(?:周|星期|礼拜)的?([一二三四五六七日天]+)的?(\d{1,2})[：:.点](\d{1,2})分?",
            ["day_of_week", "hour", "minute"],
        ),
    ]

    for pattern, fields in patterns:
        match = re.search(pattern, time)
        if match:
            params = {}
            for idx, field in enumerate(fields):
                value_str = match.group(idx + 1)

                if field == "day_of_week":
                    # 中文星期转换逻辑（保持不变）
                    converted = []
                    for char in value_str:
                        num = {
                            "日": 6,
                            "天": 6,
                            "七": 6,
                            "一": 0,
                            "二": 1,
                            "三": 2,
                            "四": 3,
                            "五": 4,
                            "六": 5,
                        }.get(char)
                        if num is None:
                            raise ValueError(f"无效的星期字符: {char}")
                        converted.append(str(num))
                    params[field] = ",".join(converted)
                else:
                    # 数值型字段校验
                    value = int(value_str)
                    validation_rules = {
                        "hour": (0, 23),
                        "minute": (0, 59),
                        "day": (1, 31),
                        "month": (1, 12),
                    }
                    if field in validation_rules:
                        min_val, max_val = validation_rules[field]
                        if not (min_val <= value <= max_val):
                            raise ValueError(f"无效的{field}值: {value}")
                    params[field] = value

            # 日期组合校验
            validate_date_params(params)

            logger.debug(
                "正则解析参数为" + ", ".join(f"{k}={v}" for k, v in params.items())
            )
            return CronTrigger(**params)

    # 无法使用正则表达式解析，采用glm-4模型解析
    params_str = await parsed_cron_time_glm4(time)
    params = ast.literal_eval(params_str)
    if isinstance(params, dict):
        return CronTrigger(**params)
    else:
        raise ValueError(f"无法解析循环时间{time}")


if __name__ == "__main__":
    test = ["每天13点30", "每小时30分", "每年12月3号15.22", "每周三14.00"]

    for s in test:
        res = parse_cron_trigger(s)
        print(res)
