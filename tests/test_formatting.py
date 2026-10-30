from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bot.formatting import format_repeat, format_when, humanize_delta
from bot.timeparse import DAILY, WEEKDAYS, WEEKLY

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=MSK)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (datetime(2026, 10, 30, 18, 30, tzinfo=MSK), "сегодня в 18:30"),
        (datetime(2026, 10, 31, 9, 0, tzinfo=MSK), "завтра в 09:00"),
        (datetime(2026, 11, 1, 9, 0, tzinfo=MSK), "послезавтра в 09:00"),
        (datetime(2026, 11, 6, 12, 0, tzinfo=MSK), "пт, 06.11 в 12:00"),
        (datetime(2027, 1, 1, 0, 0, tzinfo=MSK), "пт, 01.01.2027 в 00:00"),
    ],
)
def test_format_when(when, expected):
    assert format_when(when, NOW) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=10), "через 1 мин"),
        (timedelta(minutes=15), "через 15 мин"),
        (timedelta(hours=2, minutes=5), "через 2 ч 5 мин"),
        (timedelta(hours=3), "через 3 ч"),
        (timedelta(days=2, hours=4, minutes=30), "через 2 д 4 ч"),
    ],
)
def test_humanize_delta(delta, expected):
    assert humanize_delta(delta) == expected


def test_format_repeat():
    monday = datetime(2026, 11, 2, 10, tzinfo=MSK)
    friday = datetime(2026, 10, 30, 10, tzinfo=MSK)
    sunday = datetime(2026, 11, 1, 10, tzinfo=MSK)
    assert format_repeat(DAILY, monday) == "каждый день"
    assert format_repeat(WEEKDAYS, monday) == "по будням"
    assert format_repeat(WEEKLY, monday) == "каждый понедельник"
    assert format_repeat(WEEKLY, friday) == "каждую пятницу"
    assert format_repeat(WEEKLY, sunday) == "каждое воскресенье"
    assert format_repeat(None, monday) == ""
