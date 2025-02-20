import re
from datetime import datetime
from apscheduler.triggers.cron import CronTrigger


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
    # 解析触发器字符串
    trigger_str = str(trigger)
    pattern = r"(\w+)='([^']*)'"
    matches = re.findall(pattern, trigger_str)
    params = {m[0]: m[1] for m in matches}

    # 星期转换表
    week_map = {
        "6": "日",
        "0": "一",
        "1": "二",
        "2": "三",
        "3": "四",
        "4": "五",
        "5": "六",
        "sun": "日",
        "mon": "一",
        "tue": "二",
        "wed": "三",
        "thu": "四",
        "fri": "五",
        "sat": "六",
    }

    def parse_field(field, value):
        # 处理星期字段
        if field == "day_of_week":
            if "-" in value:
                start, end = value.split("-")
                return f"{week_map.get(start, start)}至{week_map.get(end, end)}"
            if "," in value:
                parts = sorted(
                    [week_map.get(p, p) for p in value.split(",")],
                    key=lambda x: (
                        list(week_map.values()).index(x)
                        if x in week_map.values()
                        else 7
                    ),
                )
                return "、".join(parts)
            if "/" in value:
                return f"每隔{value.split('/')[-1]}天"
            return week_map.get(value, value)

        # 处理单位映射
        units = {"year": "年", "month": "月", "day": "日", "hour": "点", "minute": "分"}
        unit = units[field]

        # 处理间隔表达式
        if "/" in value:
            return f"每隔{value.split('/')[-1]}{unit}"

        # 处理范围表达式
        if "-" in value:
            return f"{value.split('-')[0]}至{value.split('-')[1]}{unit}"

        # 处理多值情况
        if "," in value:
            return f"{value.replace(',', '、')}{unit}"

        return f"{value}{unit}"

    # 构建描述组件
    components = []
    has_date = False

    # 处理日期部分（年/月/日）
    date_fields = []
    for field in ["year", "month", "day"]:
        if field in params and params[field] != "*":
            date_fields.append(field)

    # 生成日期描述
    date_desc = []
    for field in ["year", "month", "day"]:
        if field not in params or params[field] == "*":
            continue

        parsed = parse_field(field, params[field])
        if field == "year":
            date_desc.append(f"每年{parsed.replace('年', '')}")
        elif field == "month":
            prefix = "年" if "year" in date_fields else "每年"
            date_desc.append(f"{prefix}{parsed}")
        elif field == "day":
            prefix = "" if "month" in date_fields else "每月"
            parsed_value = parsed.replace("日", "")
            date_desc.append(f"{prefix}{parsed_value}日")

    if date_desc:
        components.append("".join(date_desc))
        has_date = True

    # 处理周字段
    if "day_of_week" in params and params["day_of_week"] != "*":
        week_desc = parse_field("day_of_week", params["day_of_week"])
        components.append(f"每周{week_desc}")
        has_date = True

    # 处理时间部分
    time_desc = []
    for field in ["hour", "minute"]:
        if field in params and params[field] != "*":
            time_desc.append(parse_field(field, params[field]))

    # 生成时间描述
    if time_desc:
        time_str = "".join(time_desc)

        # 优化格式：仅当同时存在小时和分钟且为简单数字时显示为HH:MM
        if len(time_desc) == 2:
            hour_value = params.get("hour", "*")
            minute_value = params.get("minute", "*")
            if hour_value.isdigit() and minute_value.isdigit():
                formatted_hour = f"{int(hour_value):02d}"
                formatted_minute = f"{int(minute_value):02d}"
                time_str = f"{formatted_hour}:{formatted_minute}"

        # 判断是否需要时间前缀
        if "hour" in params:
            prefix = ""
            if not has_date:
                prefix = "每天"
            time_str = f"{prefix}{time_str}"
        elif "minute" in params:
            time_str = f"每小时{time_str}"

        components.append(time_str)

    return "".join(components) if components else "每时每刻"
