"""回归防线：zhipuai 依赖链已彻底移除（商店验证失败根因）。

根因回顾：zhipuai 顶层硬导入在干净环境（无 sniffio）中直接抛错，导致
插件加载失败。这里守住两件事：源码与依赖清单中不再出现 zhipuai；
插件在（无 zhipuai、无 openai 的）本环境可正常加载并完成核心离线解析。
"""

from pathlib import Path

import nonebot

import nonebot_plugin_remind

PACKAGE_DIR = Path(nonebot_plugin_remind.__file__).parent
PROJECT_ROOT = PACKAGE_DIR.parent


def test_no_zhipuai_in_sources():
    for path in PACKAGE_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "zhipuai" not in text, f"源码残留 zhipuai 引用: {path}"


def test_no_zhipuai_in_dependencies():
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "zhipuai" not in pyproject, "依赖清单残留 zhipuai"


def test_plugin_registered():
    """conftest 已完成加载；插件应出现在已加载列表中。"""
    loaded = {plugin.name for plugin in nonebot.get_loaded_plugins()}
    assert "nonebot_plugin_remind" in loaded


async def test_core_parse_available():
    """核心离线解析链路可用（不依赖任何大模型）。"""
    from nonebot_plugin_remind.parse import parse_time

    assert await parse_time("明天下午3点") is not None
