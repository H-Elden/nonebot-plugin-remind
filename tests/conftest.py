"""pytest 全局初始化：NoneBot 初始化（离线 none 驱动器）并加载本插件。

必须在测试模块收集之前（本文件导入时）完成初始化与插件加载：
测试模块会 import ``nonebot_plugin_remind`` 的子模块，而导入子模块必先
导入父包（父包会创建匹配器并要求调度器就绪），因此 NoneBot 需要先
init 再 load，与商店加载测试的语义一致。

nonebug 集成说明：
- nonebug 会话级夹具会再次调用 ``nonebot.init()``，NoneBot 的 init 幂等
  （已初始化时直接跳过），不会与上方的初始化冲突；
- 下方 ``pytest_configure`` 关闭 nonebug 的自动 lifespan，保持「调度器
  未启动、启动钩子不在测试会话中执行」的既有测试语义（任务装载相关
  用例自行直接调用 ``load_tasks()``）。
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


def pytest_configure(config: pytest.Config) -> None:
    """关闭 nonebug 自动 lifespan（见模块 docstring）。"""
    from nonebug import NONEBOT_START_LIFESPAN

    config.stash[NONEBOT_START_LIFESPAN] = False


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """测试一律禁用真实大模型兜底（防本地 .env 配置触发外呼）。"""
    from nonebot_plugin_remind.config import plugin_config

    monkeypatch.setattr(plugin_config, "remind_llm_api_key", "")


@pytest.fixture(autouse=True)
def _clean_scheduler():
    """用例结束后清空调度器，避免任务在用例间残留。"""
    yield
    from nonebot_plugin_apscheduler import scheduler

    scheduler.remove_all_jobs()


@pytest.fixture
def logs():
    """接管 NoneBot（loguru）日志的用例级 sink，返回记录消息列表。

    标准库的 caplog 抓不到 loguru 的记录（NoneBot 的 logger 不走 logging 模块），
    故统一用本夹具断言日志文案。
    """
    from nonebot.log import logger

    records: list[str] = []
    sink_id = logger.add(
        lambda message: records.append(message.record["message"]),
        level="INFO",
        format="{message}",
    )
    yield records
    logger.remove(sink_id)


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
