from datetime import datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import Database, Reminder
from bot.formatting import format_repeat, format_when, humanize_delta
from bot.keyboards import ReminderAction, created_keyboard, list_keyboard
from bot.timeparse import parse_reminder

router = Router()

MAX_TEXT_LENGTH = 1000
MAX_ACTIVE_REMINDERS = 50

HELP_TEXT = """<b>Просто напишите, когда и о чём напомнить:</b>

⏱ <code>через 15 минут проверить духовку</code>
⏱ <code>через 1ч 30м выйти из дома</code>
📅 <code>завтра в 10:00 позвонить маме</code>
📅 <code>в пятницу в 19:00 кино</code>
📅 <code>25.12 в 9:00 поздравить коллег</code>
🌙 <code>в 7 вечера тренировка</code>
🔁 <code>каждый день в 9:00 выпить витамины</code>
🔁 <code>по будням в 8:30 стендап</code>
🔁 <code>каждый понедельник в 10:00 отчёт</code>

<b>Команды</b>
/list — активные напоминания
/help — эта справка
"""


def _now(config: Config) -> datetime:
    return datetime.now(config.timezone)


def _describe(reminder: Reminder, now: datetime) -> str:
    when = format_when(reminder.remind_at, now)
    if reminder.repeat:
        local_when = reminder.remind_at.astimezone(now.tzinfo)
        return f"{when} · 🔁 {format_repeat(reminder.repeat, local_when)}"
    return f"{when} ({humanize_delta(reminder.remind_at - now)})"


def _render_list(reminders: list[Reminder], now: datetime) -> str:
    lines = [
        f"<b>{i}.</b> {escape(r.text)}\n    {_describe(r, now)}"
        for i, r in enumerate(reminders, start=1)
    ]
    return "<b>Ваши напоминания</b>\n\n" + "\n\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    name = escape(message.from_user.first_name or "друг")
    await message.answer(f"Привет, {name}! ⏰ Я напомню о чём угодно.\n\n{HELP_TEXT}")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("list"))
async def cmd_list(message: Message, db: Database, config: Config) -> None:
    reminders = await db.list_active(message.from_user.id)
    if not reminders:
        await message.answer(
            "Активных напоминаний нет. Напишите, например:\n"
            "<code>через 10 минут проверить почту</code>"
        )
        return
    await message.answer(
        _render_list(reminders, _now(config)), reply_markup=list_keyboard(reminders)
    )


@router.message(F.text)
async def create_reminder(message: Message, db: Database, config: Config) -> None:
    now = _now(config)
    parsed = parse_reminder(message.text, now)
    if parsed is None:
        await message.answer(
            "Не понял, когда напомнить 🤔\n"
            "Попробуйте так: <code>завтра в 10:00 позвонить маме</code> или /help"
        )
        return
    if parsed.when <= now:
        await message.answer("Это время уже прошло ⌛ Укажите момент в будущем.")
        return
    if len(parsed.text) > MAX_TEXT_LENGTH:
        await message.answer(f"Слишком длинный текст, максимум {MAX_TEXT_LENGTH} символов.")
        return
    if len(await db.list_active(message.from_user.id)) >= MAX_ACTIVE_REMINDERS:
        await message.answer(
            f"У вас уже {MAX_ACTIVE_REMINDERS} активных напоминаний. Удалите лишние в /list."
        )
        return

    reminder = await db.add(
        message.from_user.id, message.chat.id, parsed.text, parsed.when, parsed.repeat
    )
    await message.answer(
        f"✅ Напомню {_describe(reminder, now)}\n📝 {escape(reminder.text)}",
        reply_markup=created_keyboard(reminder.id),
    )


@router.callback_query(ReminderAction.filter())
async def on_reminder_action(
    callback: CallbackQuery, callback_data: ReminderAction, db: Database, config: Config
) -> None:
    user_id = callback.from_user.id
    reminder = await db.get(user_id, callback_data.reminder_id)
    if reminder is None:
        await callback.answer("Это напоминание уже удалено", show_alert=True)
        return

    now = _now(config)
    match callback_data.action:
        case "cancel":
            await db.delete(user_id, reminder.id)
            await callback.message.edit_text(f"✖️ <s>{escape(reminder.text)}</s>\nОтменено.")
            await callback.answer("Отменено")
        case "delete":
            await db.delete(user_id, reminder.id)
            await callback.answer(f"Удалено: {reminder.text[:50]}")
            await _refresh_list(callback, db, config)
        case "snooze":
            when = now + timedelta(minutes=callback_data.minutes)
            if reminder.repeat:
                # повторяющееся не трогаем: откладываем разовую копию
                await db.add(user_id, reminder.chat_id, reminder.text, when)
            else:
                await db.reschedule(reminder.id, when)
            await callback.message.edit_text(
                f"⏰ {escape(reminder.text)}\n\n💤 Отложено, напомню {format_when(when, now)}"
            )
            await callback.answer("Отложено")
        case "done":
            if not reminder.repeat:
                await db.delete(user_id, reminder.id)
            await callback.message.edit_text(f"✅ <s>{escape(reminder.text)}</s>")
            await callback.answer("Отлично!")
        case _:
            await callback.answer()


async def _refresh_list(callback: CallbackQuery, db: Database, config: Config) -> None:
    reminders = await db.list_active(callback.from_user.id)
    if not reminders:
        await callback.message.edit_text("Активных напоминаний больше нет.")
        return
    await callback.message.edit_text(
        _render_list(reminders, _now(config)), reply_markup=list_keyboard(reminders)
    )
