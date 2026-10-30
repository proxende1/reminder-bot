from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from bot.scheduler import ReminderScheduler
from bot.timeparse import DAILY
from tests.conftest import USER_ID

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)  # 14:00 по Москве


def make_scheduler(bot, db):
    return ReminderScheduler(bot, db, MSK, interval=1)


async def test_sends_due_one_off_and_marks_fired(bot, session, db):
    reminder = await db.add(USER_ID, USER_ID, "выпить <воды>", NOW - timedelta(seconds=5))
    await db.add(USER_ID, USER_ID, "позже", NOW + timedelta(minutes=5))

    assert await make_scheduler(bot, db).tick(NOW) == 1

    [request] = session.requests
    assert isinstance(request, SendMessage)
    assert request.chat_id == USER_ID
    assert "выпить &lt;воды&gt;" in request.text  # HTML экранирован
    assert request.reply_markup is not None  # кнопки «отложить»
    assert (await db.get(USER_ID, reminder.id)).fired
    # повторный тик ничего не шлёт
    assert await make_scheduler(bot, db).tick(NOW) == 0


async def test_repeating_is_rescheduled(bot, session, db):
    first = datetime(2026, 10, 30, 9, 0, tzinfo=MSK)
    reminder = await db.add(USER_ID, USER_ID, "витамины", first, repeat=DAILY)

    await make_scheduler(bot, db).tick(NOW)

    loaded = await db.get(USER_ID, reminder.id)
    assert not loaded.fired
    assert loaded.remind_at.astimezone(MSK) == datetime(2026, 10, 31, 9, 0, tzinfo=MSK)
    assert "каждый день" in session.requests[0].text


async def test_blocked_user_reminder_is_dropped(bot, session, db):
    async def forbidden(*args, **kwargs):
        raise TelegramForbiddenError(method=SendMessage(chat_id=1, text="x"), message="blocked")

    session.make_request = forbidden
    reminder = await db.add(USER_ID, USER_ID, "x", NOW - timedelta(seconds=1), repeat=DAILY)

    assert await make_scheduler(bot, db).tick(NOW) == 0
    assert await db.get(USER_ID, reminder.id) is None
