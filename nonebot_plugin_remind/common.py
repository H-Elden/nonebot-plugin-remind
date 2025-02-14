from pathlib import Path
from nonebot import require

require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as store


TASKS_FILE: Path = store.get_plugin_data_file("remind_tasks.json")

# 支持的时间格式
time_format = ["%Y.%m.%d.%H.%M", "%m.%d.%H.%M", "%H.%M"]
# 存储任务信息的字典
task_info = {}
