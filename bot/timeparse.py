"""Разбор времени напоминания из естественного русского текста.

Поддерживается:
    через 15 минут / через 2 часа / через полчаса / через 1ч 30м / 10m / 2ч
    в 18:30 / сегодня в 18:30 / завтра в 10:00 / послезавтра / в 7 вечера
    в пятницу в 12:00 / 25.12 в 9:00 / 01.01.2027
    каждый день в 9:00 / по будням в 8:30 / каждый понедельник в 10:00
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

DAILY = "daily"
WEEKDAYS = "weekdays"
WEEKLY = "weekly"

DEFAULT_TIME = time(9, 0)

_WEEKDAY_STEMS = ("понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресен")
_WEEKDAY_WORD = (
    r"(понедельник\w*|вторник\w*|сред[ауы]\w*|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*)"
)

_PREFIX_RE = re.compile(r"^(?:/remind(?:@\w+)?|напомни(?:\s+мне)?)(?:\s+|$)", re.IGNORECASE)

_UNIT_GROUPS = (
    ("weeks", r"недел[юиь]|нед|w"),
    ("days", r"дн[яей]+|день|д|d"),
    ("hours", r"час(?:а|ов)?|ч|h"),
    ("minutes", r"минут[уы]?|мин|м|min|m"),
)
_UNIT_RE = "|".join(f"(?P<{name}>{pattern})" for name, pattern in _UNIT_GROUPS)
_AMOUNT_RE = re.compile(rf"^(?P<num>\d{{1,4}})\s*(?:{_UNIT_RE})(?![\wё])\s*(?:и\s+)?", re.I)
_WORD_AMOUNT_RE = re.compile(r"^(?P<word>полчаса|минуту|час|день|неделю)(?![\wё])\s*", re.I)
_THROUGH_RE = re.compile(r"^через\s+", re.I)

_DAY_WORD_RE = re.compile(r"^(?P<word>сегодня|завтра|послезавтра)(?![\wё])\s*", re.I)
_WEEKDAY_RE = re.compile(rf"^(?:во?\s+)?{_WEEKDAY_WORD}(?![\wё])\s*", re.I)
_DATE_RE = re.compile(r"^(?P<d>\d{1,2})\.(?P<mo>\d{1,2})(?:\.(?P<y>\d{4}|\d{2}))?(?![\d.])\s*")
_TIME_RE = re.compile(r"^(?:в\s+)?(?P<h>\d{1,2}):(?P<m>\d{2})(?!\d)\s*", re.I)
_TIME_WORD_RE = re.compile(
    r"^(?:в\s+)?(?P<h>\d{1,2})\s*(?:час(?:а|ов)?\s+)?(?P<part>утра|дня|вечера|ночи)(?![\wё])\s*",
    re.I,
)

_REPEAT_DAILY_RE = re.compile(r"^(?:каждый\s+день|ежедневно)(?![\wё])\s*", re.I)
_REPEAT_WEEKDAYS_RE = re.compile(r"^по\s+будням(?![\wё])\s*", re.I)
_REPEAT_WEEKLY_RE = re.compile(rf"^(?:кажд(?:ый|ую|ое)|по)\s+{_WEEKDAY_WORD}(?![\wё])\s*", re.I)

_SEPARATORS = " ,.:;-—"


@dataclass(frozen=True)
class ParsedReminder:
    when: datetime
    text: str
    repeat: str | None = None


def _weekday_index(word: str) -> int:
    word = word.lower()
    return next(i for i, stem in enumerate(_WEEKDAY_STEMS) if word.startswith(stem))


def _clean_text(rest: str) -> str:
    return rest.strip().lstrip(_SEPARATORS).strip()


def _take_time(rest: str) -> tuple[time | None, str]:
    """Пытается откусить время в начале строки. None, если времени нет."""
    if m := _TIME_RE.match(rest):
        hour, minute = int(m["h"]), int(m["m"])
        if hour < 24 and minute < 60:
            return time(hour, minute), rest[m.end() :]
        raise ValueError("invalid time")
    if m := _TIME_WORD_RE.match(rest):
        hour, part = int(m["h"]), m["part"].lower()
        if not 1 <= hour <= 12:
            raise ValueError("invalid time")
        if part in ("дня", "вечера") and hour != 12:
            hour += 12
        elif part in ("утра", "ночи") and hour == 12:
            hour = 0
        return time(hour, 0), rest[m.end() :]
    return None, rest


def _next_weekday(now: datetime, weekday: int, at: time) -> datetime:
    days_ahead = (weekday - now.weekday()) % 7
    candidate = datetime.combine(now.date() + timedelta(days=days_ahead), at, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def _today_or_tomorrow(now: datetime, at: time) -> datetime:
    candidate = datetime.combine(now.date(), at, tzinfo=now.tzinfo)
    return candidate if candidate > now else candidate + timedelta(days=1)


def _parse_relative(s: str, now: datetime) -> ParsedReminder | None:
    rest = s
    through = _THROUGH_RE.match(rest)
    if through:
        rest = rest[through.end() :]

    delta = timedelta()
    while m := _AMOUNT_RE.match(rest):
        unit = next(name for name, _ in _UNIT_GROUPS if m[name])
        delta += timedelta(**{unit: int(m["num"])})
        rest = rest[m.end() :]

    # «через час», «через полчаса» — только после «через», иначе «час почитать» станет временем
    if delta == timedelta() and through and (m := _WORD_AMOUNT_RE.match(rest)):
        word = m["word"].lower()
        delta = {
            "полчаса": timedelta(minutes=30),
            "минуту": timedelta(minutes=1),
            "час": timedelta(hours=1),
            "день": timedelta(days=1),
            "неделю": timedelta(weeks=1),
        }[word]
        rest = rest[m.end() :]

    if delta == timedelta():
        return None
    return ParsedReminder(when=now + delta, text=_clean_text(rest))


def _parse_absolute(s: str, now: datetime) -> ParsedReminder | None:
    rest = s
    day: date | None = None
    weekday: int | None = None
    at: time | None = None
    roll_to_next_year = False

    # дата и время могут идти в любом порядке: «завтра в 10:00» и «в 10:00 завтра»
    for _ in range(2):
        if day is None and weekday is None:
            if m := _DAY_WORD_RE.match(rest):
                offset = {"сегодня": 0, "завтра": 1, "послезавтра": 2}[m["word"].lower()]
                day = now.date() + timedelta(days=offset)
                rest = rest[m.end() :]
                continue
            if m := _WEEKDAY_RE.match(rest):
                weekday = _weekday_index(m[1])
                rest = rest[m.end() :]
                continue
            if m := _DATE_RE.match(rest):
                year = int(m["y"]) if m["y"] else now.year
                if m["y"] and year < 100:
                    year += 2000
                roll_to_next_year = not m["y"]
                day = date(year, int(m["mo"]), int(m["d"]))  # ValueError на 31.02
                rest = rest[m.end() :]
                continue
        if at is None:
            parsed_time, rest = _take_time(rest)
            if parsed_time is not None:
                at = parsed_time
                continue
        break

    if day is None and weekday is None and at is None:
        return None

    if weekday is not None:
        when = _next_weekday(now, weekday, at or DEFAULT_TIME)
    elif day is not None:
        when = datetime.combine(day, at or DEFAULT_TIME, tzinfo=now.tzinfo)
        if when <= now and roll_to_next_year:
            when = when.replace(year=when.year + 1)
    else:
        when = _today_or_tomorrow(now, at)
    return ParsedReminder(when=when, text=_clean_text(rest))


def _parse_repeating(s: str, now: datetime) -> ParsedReminder | None:
    if m := _REPEAT_DAILY_RE.match(s):
        repeat, weekday = DAILY, None
    elif m := _REPEAT_WEEKDAYS_RE.match(s):
        repeat, weekday = WEEKDAYS, None
    elif m := _REPEAT_WEEKLY_RE.match(s):
        repeat, weekday = WEEKLY, _weekday_index(m[1])
    else:
        return None

    at, rest = _take_time(s[m.end() :])
    at = at or DEFAULT_TIME

    if repeat == WEEKLY:
        when = _next_weekday(now, weekday, at)
    else:
        when = _today_or_tomorrow(now, at)
        if repeat == WEEKDAYS:
            while when.weekday() >= 5:
                when += timedelta(days=1)
    return ParsedReminder(when=when, text=_clean_text(rest), repeat=repeat)


def parse_reminder(text: str, now: datetime) -> ParsedReminder | None:
    """Возвращает напоминание или None, если не удалось понять время или нет текста.

    `now` должен быть aware-datetime в часовом поясе пользователя. Время в прошлом
    («сегодня в 08:00», когда уже 10:00) парсер возвращает как есть: решение за вызывающим.
    """
    s = " ".join(text.split())
    s = _PREFIX_RE.sub("", s, count=1)
    if not s:
        return None
    try:
        result = _parse_repeating(s, now) or _parse_relative(s, now) or _parse_absolute(s, now)
    except ValueError:
        return None
    if result is None or not result.text:
        return None
    return result


def next_occurrence(when: datetime, repeat: str, now: datetime) -> datetime:
    """Следующее срабатывание повторяющегося напоминания строго после `now`.

    `when` — в локальном поясе: прибавление дней сохраняет «настенное» время и при переходе
    на летнее/зимнее время.
    """
    step = timedelta(weeks=1) if repeat == WEEKLY else timedelta(days=1)
    candidate = when
    while candidate <= now or (repeat == WEEKDAYS and candidate.weekday() >= 5):
        candidate += step
    return candidate
