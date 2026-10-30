"""Фоновый цикл: раз в N секунд достаёт созревшие напоминания и отправляет их.

Состояние целиком в БД, поэтому после перезапуска бота ничего не теряется:
пропущенные за время простоя напоминания придут при первом же тике.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.db import Database, Reminder
from bot.formatting import format_repeat
from bot.keyboards import fired_keyboard
from bot.timeparse import next_occurrence

logger = logging.getLogger(__name__)

FIRED_TTL = timedelta(days=7)


class ReminderScheduler:
    def __init__(self, bot: Bot, db: Database, tz: ZoneInfo, interval: float = 10) -> None:
        self._bot = bot
        self._db = db
        self._tz = tz
        self._interval = interval

    async def tick(self, now: datetime | None = None) -> int:
        """Отправляет все созревшие напоминания. Возвращает число отправленных."""
        now = now or datetime.now(UTC)
        sent = 0
        for reminder in await self._db.due(now):
            if not await self._deliver(reminder):
                continue
            sent += 1
            if reminder.repeat:
                local_when = reminder.remind_at.astimezone(self._tz)
                await self._db.reschedule(
                    reminder.id, next_occurrence(local_when, reminder.repeat, now)
                )
            else:
                await self._db.mark_fired(reminder.id)
        await self._db.purge_fired(now - FIRED_TTL)
        return sent

    async def _deliver(self, reminder: Reminder) -> bool:
        text = f"⏰ <b>Напоминание</b>\n\n{escape(reminder.text)}"
        if reminder.repeat:
            local_when = reminder.remind_at.astimezone(self._tz)
            text += f"\n\n🔁 {format_repeat(reminder.repeat, local_when)}"
        try:
            await self._bot.send_message(
                reminder.chat_id, text, reply_markup=fired_keyboard(reminder.id)
            )
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            # пользователь заблокировал бота или чат удалён: дальше слать некуда
            logger.warning("Cannot deliver reminder %s: %s", reminder.id, exc)
            await self._db.delete_by_id(reminder.id)
            return False
        return True

    async def run(self) -> None:
        logger.info("Scheduler started, interval=%ss", self._interval)
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self._interval)
