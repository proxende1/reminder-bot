"""Человекочитаемые даты: «завтра в 10:00», «через 2 ч 5 мин», «по будням»."""

from datetime import datetime, timedelta

from bot.timeparse import DAILY, WEEKDAYS, WEEKLY

WEEKDAYS_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
WEEKDAYS_ACC = (
    "понедельник",
    "вторник",
    "среду",
    "четверг",
    "пятницу",
    "субботу",
    "воскресенье",
)


def format_when(when: datetime, now: datetime) -> str:
    when = when.astimezone(now.tzinfo)
    days = (when.date() - now.date()).days
    clock = when.strftime("%H:%M")
    if days == 0:
        return f"сегодня в {clock}"
    if days == 1:
        return f"завтра в {clock}"
    if days == 2:
        return f"послезавтра в {clock}"
    date_part = when.strftime("%d.%m") if when.year == now.year else when.strftime("%d.%m.%Y")
    return f"{WEEKDAYS_SHORT[when.weekday()]}, {date_part} в {clock}"


def humanize_delta(delta: timedelta) -> str:
    minutes = max(1, round(delta.total_seconds() / 60))
    days, minutes = divmod(minutes, 60 * 24)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if days:
        parts.append(f"{days} д")
    if hours:
        parts.append(f"{hours} ч")
    if minutes and not days:
        parts.append(f"{minutes} мин")
    return "через " + " ".join(parts or ["1 мин"])


def format_repeat(repeat: str | None, when: datetime) -> str:
    if repeat == DAILY:
        return "каждый день"
    if repeat == WEEKDAYS:
        return "по будням"
    if repeat == WEEKLY:
        day = WEEKDAYS_ACC[when.weekday()]
        prefix = "каждое" if day == "воскресенье" else "каждую" if day.endswith("у") else "каждый"
        return f"{prefix} {day}"
    return ""
