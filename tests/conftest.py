"""pytest 全局初始化：NoneBot 初始化（离线 none 驱动器）并加载本插件。

必须在测试模块收集之前（本文件导入时）完成初始化与插件加载：
测试模块会 import ``nonebot_plugin_remind`` 的子模块，而导入子模块必先
导入父包（父包会创建匹配器并要求调度器就绪），因此 NoneBot 需要先
init 再 load，与商店加载测试的语义一致。
"""

import os
from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 固定测试环境与数据目录（须在 nonebot.init 之前设置）
os.environ["ENVIRONMENT"] = "test"
os.environ["LOCALSTORE_DATA_DIR"] = str(PROJECT_ROOT / "data")

nonebot.init(driver="~none")
driver = nonebot.get_driver()
driver.register_adapter(OnebotV11Adapter)
nonebot.load_from_toml(str(PROJECT_ROOT / "pyproject.toml"))
