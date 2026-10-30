from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bot.timeparse import DAILY, WEEKDAYS, WEEKLY, next_occurrence, parse_reminder

MSK = ZoneInfo("Europe/Moscow")
# пятница, 30 октября 2026, 14:00
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=MSK)


def at(day: int, hour: int, minute: int = 0, month: int = 10, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=MSK)


@pytest.mark.parametrize(
    ("text", "delta", "body"),
    [
        ("через 15 минут проверить духовку", timedelta(minutes=15), "проверить духовку"),
        ("через 2 часа созвон", timedelta(hours=2), "созвон"),
        ("через 1 час 30 минут выйти", timedelta(hours=1, minutes=30), "выйти"),
        ("через 1ч 30м выйти", timedelta(hours=1, minutes=30), "выйти"),
        ("через 3 дня оплатить", timedelta(days=3), "оплатить"),
        ("через 2 недели к врачу", timedelta(weeks=2), "к врачу"),
        ("через полчаса чай", timedelta(minutes=30), "чай"),
        ("через час обед", timedelta(hours=1), "обед"),
        ("через минуту тест", timedelta(minutes=1), "тест"),
        ("10m размяться", timedelta(minutes=10), "размяться"),
        ("2ч поесть", timedelta(hours=2), "поесть"),
        ("напомни через 5 мин позвонить", timedelta(minutes=5), "позвонить"),
        ("Напомни мне через 5 мин позвонить", timedelta(minutes=5), "позвонить"),
        ("/remind 20 min stretch", timedelta(minutes=20), "stretch"),
    ],
)
def test_relative(text, delta, body):
    parsed = parse_reminder(text, NOW)
    assert parsed is not None
    assert parsed.when == NOW + delta
    assert parsed.text == body
    assert parsed.repeat is None


@pytest.mark.parametrize(
    ("text", "when", "body"),
    [
        ("в 18:30 забрать посылку", at(30, 18, 30), "забрать посылку"),
        ("в 9:00 планёрка", at(31, 9), "планёрка"),  # 9:00 уже прошло → завтра
        ("18:30 спорт", at(30, 18, 30), "спорт"),
        ("сегодня в 20:00 сериал", at(30, 20), "сериал"),
        ("завтра в 10:00 позвонить маме", at(31, 10), "позвонить маме"),
        ("в 10:00 завтра позвонить маме", at(31, 10), "позвонить маме"),
        ("завтра купить хлеб", at(31, 9), "купить хлеб"),
        ("послезавтра в 7:15 поезд", at(1, 7, 15, month=11), "поезд"),
        ("в 7 вечера тренировка", at(30, 19), "тренировка"),
        ("завтра в 8 утра пробежка", at(31, 8), "пробежка"),
        ("в 12 дня обед", at(31, 12), "обед"),
        ("в понедельник в 10:00 отчёт", at(2, 10, month=11), "отчёт"),
        ("во вторник созвон", at(3, 9, month=11), "созвон"),
        ("в пятницу в 18:00 бар", at(30, 18), "бар"),  # сегодня пятница и 18:00 ещё впереди
        ("в пятницу в 12:00 бар", at(6, 12, month=11), "бар"),  # 12:00 прошло → через неделю
        ("в среду кино", at(4, 9, month=11), "кино"),
        ("25.12 в 9:00 поздравить коллег", at(25, 9, month=12), "поздравить коллег"),
        ("01.01.2027 0:00 с новым годом", at(1, 0, month=1, year=2027), "с новым годом"),
        ("15.03 налоговая", at(15, 9, month=3, year=2027), "налоговая"),  # прошло → след. год
        ("завтра в 10:00, позвонить", at(31, 10), "позвонить"),
    ],
)
def test_absolute(text, when, body):
    parsed = parse_reminder(text, NOW)
    assert parsed is not None
    assert parsed.when == when
    assert parsed.text == body


@pytest.mark.parametrize(
    ("text", "when", "repeat", "body"),
    [
        ("каждый день в 9:00 витамины", at(31, 9), DAILY, "витамины"),
        ("каждый день в 21:00 дневник", at(30, 21), DAILY, "дневник"),
        ("ежедневно полить цветы", at(31, 9), DAILY, "полить цветы"),
        ("по будням в 8:30 стендап", at(2, 8, 30, month=11), WEEKDAYS, "стендап"),  # сб/вс пропуск
        ("по будням в 15:00 обход", at(30, 15), WEEKDAYS, "обход"),
        ("каждый понедельник в 10:00 отчёт", at(2, 10, month=11), WEEKLY, "отчёт"),
        ("каждую пятницу в 18:00 пятничный созвон", at(30, 18), WEEKLY, "пятничный созвон"),
        ("каждое воскресенье уборка", at(1, 9, month=11), WEEKLY, "уборка"),
        ("по средам в 19:00 йога", at(4, 19, month=11), WEEKLY, "йога"),
        ("по понедельникам планёрка", at(2, 9, month=11), WEEKLY, "планёрка"),
    ],
)
def test_repeating(text, when, repeat, body):
    parsed = parse_reminder(text, NOW)
    assert parsed is not None
    assert parsed.when == when
    assert parsed.repeat == repeat
    assert parsed.text == body


def test_past_time_today_is_returned_for_caller_to_reject():
    parsed = parse_reminder("сегодня в 08:00 зарядка", NOW)
    assert parsed is not None
    assert parsed.when < NOW


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "напомни",
        "просто текст без времени",
        "через 10 минут",  # нет текста
        "завтра в 10:00",
        "в 25:00 что-то",
        "в 10:75 что-то",
        "31.02 в 9:00 несуществующая дата",
        "час почитать",  # без «через» это не время
        "в 15 утра странно",
    ],
)
def test_invalid(text):
    assert parse_reminder(text, NOW) is None


def test_whitespace_is_normalized():
    parsed = parse_reminder("  через   5   минут   выпить   воды ", NOW)
    assert parsed.text == "выпить воды"


class TestNextOccurrence:
    def test_daily(self):
        assert next_occurrence(at(30, 9), DAILY, at(30, 9)) == at(31, 9)

    def test_daily_catches_up_after_downtime(self):
        # бот лежал три дня — следующее срабатывание всё равно в будущем
        assert next_occurrence(at(27, 9), DAILY, at(30, 14)) == at(31, 9)

    def test_weekdays_skip_weekend(self):
        assert next_occurrence(at(30, 9), WEEKDAYS, at(30, 9)) == at(2, 9, month=11)

    def test_weekly(self):
        assert next_occurrence(at(30, 18), WEEKLY, at(30, 18)) == at(6, 18, month=11)

    def test_keeps_wall_clock_across_dst(self):
        berlin = ZoneInfo("Europe/Berlin")  # 25.10.2026 — переход на зимнее время
        before = datetime(2026, 10, 24, 9, 0, tzinfo=berlin)
        after = next_occurrence(before, DAILY, before)
        assert after.hour == 9
        assert after.utcoffset() != before.utcoffset()
