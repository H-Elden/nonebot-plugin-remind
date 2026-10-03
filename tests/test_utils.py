"""utils 模块单元测试：at 转文本、昵称获取、时长格式化与任务过滤。"""

from datetime import datetime, timedelta

from nonebot.adapters.onebot.v11 import Message

import nonebot_plugin_remind.utils as utils


class _FakeBot:
    """仅返回预设结果的假 Bot（覆盖 call_api 用法）。"""

    def __init__(self, *, result=None, error: Exception | None = None):
        self._result = result
        self._error = error

    async def call_api(self, api: str, **data):
        if self._error is not None:
            raise self._error
        return self._result


def _patch_bot(monkeypatch, bot: _FakeBot) -> None:
    monkeypatch.setattr(utils.nonebot, "get_bot", lambda: bot)


async def test_get_user_nickname_variants(monkeypatch):
    """优先取群名片，其次昵称；查不到或调用失败回退「未知用户」。"""
    _patch_bot(
        monkeypatch,
        _FakeBot(result=[{"user_id": 111, "card": "卡片", "nickname": "昵称"}]),
    )
    assert await utils.get_user_nickname(1, 111) == "卡片"

    _patch_bot(
        monkeypatch, _FakeBot(result=[{"user_id": 111, "card": "", "nickname": "昵称"}])
    )
    assert await utils.get_user_nickname(1, 111) == "昵称"

    _patch_bot(monkeypatch, _FakeBot(result=[]))
    assert await utils.get_user_nickname(1, 111) == "未知用户"

    _patch_bot(monkeypatch, _FakeBot(error=RuntimeError("网络错误")))
    assert await utils.get_user_nickname(1, 111) == "未知用户"


async def test_at_to_text_variants():
    """at 段：带昵称直接用；全体；私聊占位；非 at 段原样拼接。"""
    assert (
        await utils.at_to_text(1, Message("[CQ:at,qq=111,name=@昵称]")) == "[at 昵称]"
    )
    assert await utils.at_to_text(1, Message("[CQ:at,qq=all]")) == "[at 全体成员]"
    assert await utils.at_to_text(None, Message("[CQ:at,qq=111]")) == "[私聊]"
    assert (
        await utils.at_to_text(1, Message("前缀") + Message("[CQ:at,qq=all]"))
        == "前缀[at 全体成员]"
    )


def test_format_timedelta_variants():
    assert (
        utils.format_timedelta(timedelta(days=2, hours=3, minutes=5)) == "2天3小时5分钟"
    )
    assert utils.format_timedelta(timedelta(hours=1)) == "1小时"
    assert utils.format_timedelta(timedelta(minutes=30)) == "30分钟"
    assert utils.format_timedelta(timedelta(seconds=45)) == "45秒"


def _task(
    task_id: str,
    *,
    kind: str = "datetime",
    user: str = "10001",
    group_id: int | None = 500,
    is_group: bool = True,
    when: datetime | None = None,
) -> dict:
    return {
        "task_id": task_id,
        "reminder_user_id": user,
        "user_ids": Message(),
        "type": kind,
        "remind_time": when or (datetime.now() + timedelta(hours=1)),
        "reminder_message": Message(task_id),
        "is_group": is_group,
        "group_id": group_id,
    }


def test_get_user_tasks_filters_and_sorts(isolated, monkeypatch):
    """群聊只看本群、按提醒时间排序；私聊默认全部、可配置仅私聊。"""
    _, task_info = isolated
    now = datetime.now()
    task_info["t_early"] = _task("t_early", when=now + timedelta(hours=1))
    task_info["t_late"] = _task("t_late", when=now + timedelta(hours=3))
    task_info["t_priv"] = _task(
        "t_priv", group_id=10001, is_group=False, when=now + timedelta(hours=2)
    )
    task_info["t_other"] = _task(
        "t_other", user="99999", when=now + timedelta(minutes=10)
    )

    group_tasks = utils.get_user_tasks("10001", 500, True)
    assert [t["task_id"] for t in group_tasks] == ["t_early", "t_late"]

    all_tasks = utils.get_user_tasks("10001", None, True)
    assert [t["task_id"] for t in all_tasks] == ["t_early", "t_priv", "t_late"]

    monkeypatch.setattr(utils.plugin_config, "remind_private_list_all", False)
    only_private = utils.get_user_tasks("10001", None, False)
    assert [t["task_id"] for t in only_private] == ["t_priv"]


def test_get_user_cron_tasks_filters(isolated, monkeypatch):
    """循环任务列表只含 CronTrigger / IntervalTrigger 两类；私聊可配置仅私聊。"""
    _, task_info = isolated
    task_info["c1"] = _task("c1", kind="CronTrigger")
    task_info["c2"] = _task("c2", kind="IntervalTrigger")
    task_info["d1"] = _task("d1", kind="datetime")

    tasks = utils.get_user_cron_tasks("10001", 500)
    assert [t["task_id"] for t in tasks] == ["c1", "c2"]

    monkeypatch.setattr(utils.plugin_config, "remind_private_list_all", False)
    assert utils.get_user_cron_tasks("10001", None) == []
