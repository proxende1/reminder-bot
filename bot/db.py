"""Хранилище напоминаний на SQLite. Время храним в UTC.

Разовое напоминание после срабатывания не удаляется сразу, а помечается `fired`,
чтобы под ним работали кнопки «отложить». Старые сработавшие чистит планировщик.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    chat_id    INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    remind_at  TEXT    NOT NULL,
    repeat     TEXT,
    fired      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (fired, remind_at);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders (user_id, fired);
"""


@dataclass(frozen=True)
class Reminder:
    id: int
    user_id: int
    chat_id: int
    text: str
    remind_at: datetime
    repeat: str | None
    fired: bool


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _row_to_reminder(row: aiosqlite.Row) -> Reminder:
    return Reminder(
        id=row["id"],
        user_id=row["user_id"],
        chat_id=row["chat_id"],
        text=row["text"],
        remind_at=datetime.fromisoformat(row["remind_at"]),
        repeat=row["repeat"],
        fired=bool(row["fired"]),
    )


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def add(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        remind_at: datetime,
        repeat: str | None = None,
    ) -> Reminder:
        cursor = await self.conn.execute(
            "INSERT INTO reminders (user_id, chat_id, text, remind_at, repeat, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, text, _ts(remind_at), repeat, _ts(datetime.now(UTC))),
        )
        await self.conn.commit()
        return Reminder(
            id=cursor.lastrowid,
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            remind_at=datetime.fromisoformat(_ts(remind_at)),
            repeat=repeat,
            fired=False,
        )

    async def get(self, user_id: int, reminder_id: int) -> Reminder | None:
        async with self.conn.execute(
            "SELECT * FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_reminder(row) if row else None

    async def list_active(self, user_id: int) -> list[Reminder]:
        async with self.conn.execute(
            "SELECT * FROM reminders WHERE user_id = ? AND fired = 0 ORDER BY remind_at, id",
            (user_id,),
        ) as cursor:
            return [_row_to_reminder(row) for row in await cursor.fetchall()]

    async def delete(self, user_id: int, reminder_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def delete_by_id(self, reminder_id: int) -> None:
        await self.conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await self.conn.commit()

    async def due(self, now: datetime) -> list[Reminder]:
        async with self.conn.execute(
            "SELECT * FROM reminders WHERE fired = 0 AND remind_at <= ? ORDER BY remind_at, id",
            (_ts(now),),
        ) as cursor:
            return [_row_to_reminder(row) for row in await cursor.fetchall()]

    async def mark_fired(self, reminder_id: int) -> None:
        await self.conn.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))
        await self.conn.commit()

    async def reschedule(self, reminder_id: int, remind_at: datetime) -> None:
        await self.conn.execute(
            "UPDATE reminders SET remind_at = ?, fired = 0 WHERE id = ?",
            (_ts(remind_at), reminder_id),
        )
        await self.conn.commit()

    async def purge_fired(self, older_than: datetime) -> int:
        cursor = await self.conn.execute(
            "DELETE FROM reminders WHERE fired = 1 AND remind_at < ?", (_ts(older_than),)
        )
        await self.conn.commit()
        return cursor.rowcount
