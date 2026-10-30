from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Reminder

SNOOZE_OPTIONS = ((10, "+10 мин"), (60, "+1 час"), (24 * 60, "Завтра"))


class ReminderAction(CallbackData, prefix="rem"):
    action: str  # cancel | delete | snooze | done
    reminder_id: int
    minutes: int = 0


def created_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✖️ Отменить", callback_data=ReminderAction(action="cancel", reminder_id=reminder_id)
    )
    return builder.as_markup()


def fired_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for minutes, label in SNOOZE_OPTIONS:
        builder.button(
            text=label,
            callback_data=ReminderAction(action="snooze", reminder_id=reminder_id, minutes=minutes),
        )
    builder.button(
        text="✅ Готово", callback_data=ReminderAction(action="done", reminder_id=reminder_id)
    )
    builder.adjust(3, 1)
    return builder.as_markup()


def list_keyboard(reminders: list[Reminder]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for number, reminder in enumerate(reminders, start=1):
        builder.button(
            text=f"🗑 {number}",
            callback_data=ReminderAction(action="delete", reminder_id=reminder.id),
        )
    builder.adjust(5)
    return builder.as_markup()
