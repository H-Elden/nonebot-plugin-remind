"""正确性细节测试：批量删除参数解析等。"""

import pytest

from nonebot_plugin_remind import _parse_task_indexes


def test_parse_task_indexes_sorted_and_deduped():
    indexes, _ = _parse_task_indexes("5 3 1")
    assert indexes == [0, 2, 4]

    indexes, _ = _parse_task_indexes("1 1 2")
    assert indexes == [0, 1]

    indexes, _ = _parse_task_indexes("2-4 1")
    assert indexes == [0, 1, 2, 3]


def test_parse_task_indexes_rejects_bad_input():
    """参数错误一律给面向用户的纯文案，不带异常类型前缀。"""
    with pytest.raises(ValueError, match="起始序号大于结束序号。"):
        _parse_task_indexes("3-1")
    with pytest.raises(ValueError, match="序号应写成“1 3-6”这样的形式。"):
        _parse_task_indexes("1-2-3")
