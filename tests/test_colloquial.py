"""colloquial 模块单元测试：口语化展示各分支（锁定现状）。"""

from datetime import datetime, timedelta
from typing import cast

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from nonebot_plugin_remind import colloquial as cl

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def test_colloquial_time_rejects_unknown_type():
    with pytest.raises(TypeError):
        cl.colloquial_time(cast(datetime, "不是时间"))


def test_colloquial_datetime_date_branches():
    today = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
    assert cl.colloquial_datetime(today) == "今天上午9点15分"

    tomorrow = today + timedelta(days=1)
    assert (
        cl.colloquial_datetime(tomorrow)
        == f"明天({_WEEKDAYS[tomorrow.weekday()]})上午9点15分"
    )

    day_after = today + timedelta(days=2)
    assert (
        cl.colloquial_datetime(day_after)
        == f"后天({_WEEKDAYS[day_after.weekday()]})上午9点15分"
    )

    later = today + timedelta(days=5)
    assert cl.colloquial_datetime(later) == (
        f"5天后({later.month}月{later.day}号 {_WEEKDAYS[later.weekday()]})上午9点15分"
    )

    past = today - timedelta(days=1)
    assert (
        cl.colloquial_datetime(past) == f"1天前({_WEEKDAYS[past.weekday()]})上午9点15分"
    )

    next_year = today.replace(year=today.year + 1, month=6, day=20)
    assert cl.colloquial_datetime(next_year) == (
        f"明年6月20号({_WEEKDAYS[next_year.weekday()]})上午9点15分"
    )

    after_two = today.replace(year=today.year + 2, month=6, day=20)
    assert cl.colloquial_datetime(after_two) == (
        f"后年6月20号({_WEEKDAYS[after_two.weekday()]})上午9点15分"
    )

    far = today.replace(year=today.year + 3, month=6, day=20)
    assert cl.colloquial_datetime(far) == (
        f"{far.year}年6月20号({_WEEKDAYS[far.weekday()]})上午9点15分"
    )


def test_colloquial_datetime_period_and_minute_branches():
    base = datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
    assert cl.colloquial_datetime(base) == "今天凌晨3点整"
    assert cl.colloquial_datetime(base.replace(hour=6, minute=30)) == "今天清晨6点半"
    assert cl.colloquial_datetime(base.replace(hour=9, minute=5)) == "今天上午9点5分"
    assert cl.colloquial_datetime(base.replace(hour=12, minute=5)) == "今天中午12点5分"
    assert cl.colloquial_datetime(base.replace(hour=15, minute=30)) == "今天下午3点半"
    assert cl.colloquial_datetime(base.replace(hour=17, minute=45)) == "今天傍晚5点45分"
    assert cl.colloquial_datetime(base.replace(hour=21, minute=0)) == "今天晚上9点整"
    assert (
        cl.colloquial_datetime(base.replace(hour=23, minute=10)) == "今天夜里11点10分"
    )


def test_colloquial_crontrigger_variants():
    assert cl.colloquial_crontrigger(CronTrigger(hour=8, minute=30)) == "每天08:30"
    assert (
        cl.colloquial_crontrigger(CronTrigger(day_of_week="mon", hour=14, minute=0))
        == "每周一14:00"
    )
    assert (
        cl.colloquial_crontrigger(CronTrigger(day_of_week="0-4", hour=9, minute=0))
        == "每周一至五09:00"
    )
    assert (
        cl.colloquial_crontrigger(CronTrigger(day_of_week="0,2,4", hour=9, minute=0))
        == "每周一、三、五09:00"
    )
    assert (
        cl.colloquial_crontrigger(CronTrigger(month=10, day=1, hour=8, minute=0))
        == "每年10月1日08:00"
    )
    assert (
        cl.colloquial_crontrigger(
            CronTrigger(year=2027, month=10, day=1, hour=8, minute=0)
        )
        == "每年2027年10月1日08:00"
    )
    assert cl.colloquial_crontrigger(CronTrigger(minute=15)) == "每小时15分"
    assert cl.colloquial_crontrigger(CronTrigger(hour="*/2")) == "每天每隔2点"
    assert cl.colloquial_crontrigger(CronTrigger(hour="9-17")) == "每天9至17点"
    assert cl.colloquial_crontrigger(CronTrigger(minute="0,30")) == "每小时0、30分"
    assert cl.colloquial_crontrigger(CronTrigger()) == "每时每刻"


def test_colloquial_intervaltrigger_variants():
    assert cl.colloquial_intervaltrigger(IntervalTrigger(weeks=2)) == "每隔 2 周"
    assert cl.colloquial_intervaltrigger(IntervalTrigger(days=3)) == "每隔 3 天"
    assert cl.colloquial_intervaltrigger(IntervalTrigger(hours=2)) == "每隔 2 小时"
    assert cl.colloquial_intervaltrigger(IntervalTrigger(minutes=45)) == "每隔 45 分钟"
    assert cl.colloquial_intervaltrigger(IntervalTrigger(seconds=90)) == "每隔 90 秒"


def test_colloquial_datetime_passthrough_for_non_datetime():
    assert cl.colloquial_datetime(cast(datetime, "原样返回")) == "原样返回"


def test_colloquial_crontrigger_weekday_step():
    assert (
        cl.colloquial_crontrigger(CronTrigger(day_of_week="*/2", hour=14, minute=0))
        == "每周每隔2天14:00"
    )
