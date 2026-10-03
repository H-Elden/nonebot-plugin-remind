"""正确性细节测试：批量删除参数解析等。"""

from nonebot_plugin_remind import _parse_task_indexes


def test_parse_task_indexes_sorted_and_deduped():
    indexes, _ = _parse_task_indexes("5 3 1")
    assert indexes == [0, 2, 4]

    indexes, _ = _parse_task_indexes("1 1 2")
    assert indexes == [0, 1]

    indexes, _ = _parse_task_indexes("2-4 1")
    assert indexes == [0, 1, 2, 3]
