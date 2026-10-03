from pathlib import Path

from nonebot import require

require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as store

TASKS_FILE: Path = store.get_plugin_data_file("remind_tasks.json")

# 存储任务信息的字典
task_info = {}

# 循环提醒的任务类型（CronTrigger 与 IntervalTrigger 均视为循环任务）
RECURRING_TYPES = ("CronTrigger", "IntervalTrigger")
