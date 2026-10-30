"""Сквозные тесты: апдейт → диспетчер aiogram → хендлер → БД → запрос к API."""

from datetime import UTC, datetime, timedelta

from aiogram.methods import EditMessageText, SendMessage

from bot.handlers import MAX_ACTIVE_REMINDERS
from bot.keyboards import ReminderAction
from bot.timeparse import DAILY
from tests.conftest import USER_ID, callback_update, message_update


async def feed(dispatcher, bot, db, config, update):
    await dispatcher.feed_update(bot, update, db=db, config=config)


def texts(session):
    return [r.text for r in session.requests if isinstance(r, (SendMessage, EditMessageText))]


async def test_start(dispatcher, bot, session, db, config):
    await feed(dispatcher, bot, db, config, message_update("/start"))
    assert "Привет, Тест" in texts(session)[0]


async def test_create_relative_reminder(dispatcher, bot, session, db, config):
    before = datetime.now(UTC)
    await feed(dispatcher, bot, db, config, message_update("через 15 минут проверить духовку"))

    [reminder] = await db.list_active(USER_ID)
    assert reminder.text == "проверить духовку"
    assert reminder.chat_id == USER_ID
    expected = before + timedelta(minutes=15)
    assert abs((reminder.remind_at - expected).total_seconds()) < 5
    assert "Напомню" in texts(session)[0]
    assert "через 15 мин" in texts(session)[0]


async def test_unparseable_text(dispatcher, bot, session, db, config):
    await feed(dispatcher, bot, db, config, message_update("просто так"))
    assert "Не понял" in texts(session)[0]
    assert await db.list_active(USER_ID) == []


async def test_past_time_rejected(dispatcher, bot, session, db, config):
    await feed(dispatcher, bot, db, config, message_update("сегодня в 00:00 вчерашний день"))
    # в 00:00 ровно тест пройдёт тоже: время «сегодня в 00:00» не может быть в будущем
    assert "уже прошло" in texts(session)[0]


async def test_active_limit(dispatcher, bot, session, db, config):
    later = datetime.now(UTC) + timedelta(days=1)
    for i in range(MAX_ACTIVE_REMINDERS):
        await db.add(USER_ID, USER_ID, f"r{i}", later)
    await feed(dispatcher, bot, db, config, message_update("через 5 минут ещё одно"))
    assert "Удалите лишние" in texts(session)[0]


async def test_list_shows_reminders(dispatcher, bot, session, db, config):
    later = datetime.now(UTC) + timedelta(hours=3)
    await db.add(USER_ID, USER_ID, "первое", later)
    await db.add(USER_ID, USER_ID, "витамины", later, repeat=DAILY)
    await feed(dispatcher, bot, db, config, message_update("/list"))
    text = texts(session)[0]
    assert "первое" in text and "витамины" in text and "каждый день" in text


async def test_cancel_callback(dispatcher, bot, session, db, config):
    reminder = await db.add(USER_ID, USER_ID, "x", datetime.now(UTC) + timedelta(hours=1))
    data = ReminderAction(action="cancel", reminder_id=reminder.id).pack()
    await feed(dispatcher, bot, db, config, callback_update(data))
    assert await db.get(USER_ID, reminder.id) is None
    assert "Отменено" in texts(session)[0]


async def test_snooze_one_off(dispatcher, bot, session, db, config):
    reminder = await db.add(USER_ID, USER_ID, "x", datetime.now(UTC) - timedelta(minutes=1))
    await db.mark_fired(reminder.id)
    data = ReminderAction(action="snooze", reminder_id=reminder.id, minutes=10).pack()
    await feed(dispatcher, bot, db, config, callback_update(data))

    loaded = await db.get(USER_ID, reminder.id)
    assert not loaded.fired
    assert loaded.remind_at > datetime.now(UTC) + timedelta(minutes=9)


async def test_snooze_repeating_creates_copy(dispatcher, bot, session, db, config):
    series = await db.add(USER_ID, USER_ID, "x", datetime.now(UTC) + timedelta(days=1), DAILY)
    data = ReminderAction(action="snooze", reminder_id=series.id, minutes=60).pack()
    await feed(dispatcher, bot, db, config, callback_update(data))

    active = await db.list_active(USER_ID)
    assert len(active) == 2
    assert await db.get(USER_ID, series.id) == series  # серия не изменилась


async def test_done_removes_one_off(dispatcher, bot, session, db, config):
    reminder = await db.add(USER_ID, USER_ID, "x", datetime.now(UTC))
    await db.mark_fired(reminder.id)
    data = ReminderAction(action="done", reminder_id=reminder.id).pack()
    await feed(dispatcher, bot, db, config, callback_update(data))
    assert await db.get(USER_ID, reminder.id) is None


async def test_delete_from_list(dispatcher, bot, session, db, config):
    reminder = await db.add(USER_ID, USER_ID, "x", datetime.now(UTC) + timedelta(hours=1))
    data = ReminderAction(action="delete", reminder_id=reminder.id).pack()
    await feed(dispatcher, bot, db, config, callback_update(data))
    assert await db.get(USER_ID, reminder.id) is None
    assert "больше нет" in texts(session)[-1]
