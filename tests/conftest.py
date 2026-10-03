"""pytest 全局初始化：NoneBot 初始化（离线 none 驱动器）并加载本插件。

必须在测试模块收集之前（本文件导入时）完成初始化与插件加载：
测试模块会 import ``nonebot_plugin_remind`` 的子模块，而导入子模块必先
导入父包（父包会创建匹配器并要求调度器就绪），因此 NoneBot 需要先
init 再 load，与商店加载测试的语义一致。
"""

import os
from pathlib import Path

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 固定测试环境与数据目录（须在 nonebot.init 之前设置）
os.environ["ENVIRONMENT"] = "test"
os.environ["LOCALSTORE_DATA_DIR"] = str(PROJECT_ROOT / "data")

nonebot.init(driver="~none")
driver = nonebot.get_driver()
driver.register_adapter(OnebotV11Adapter)
nonebot.load_from_toml(str(PROJECT_ROOT / "pyproject.toml"))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """隔离任务文件与全局任务字典，返回 (任务文件路径, 新字典)。

    各模块的 TASKS_FILE / task_info 绑定统一替换到临时目录与同一份新字典，
    避免测试间互相污染。
    """
    import nonebot_plugin_remind
    import nonebot_plugin_remind.data_source as data_source
    import nonebot_plugin_remind.utils as utils
    from nonebot_plugin_remind import common

    tasks_file = tmp_path / "remind_tasks.json"
    fresh: dict = {}
    for module in (common, utils, nonebot_plugin_remind):
        monkeypatch.setattr(module, "TASKS_FILE", tasks_file)
    for module in (common, utils, nonebot_plugin_remind, data_source):
        monkeypatch.setattr(module, "task_info", fresh)
    return tasks_file, fresh
