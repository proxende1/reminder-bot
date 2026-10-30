"""Общие фикстуры: бот с фейковой сессией, которая записывает запросы к Telegram API."""

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.config import Config
from bot.db import Database
from bot.handlers import router

USER_ID = 100500


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        returning = getattr(method, "__returning__", None)
        if returning is Message or "Message" in str(returning):
            return Message(
                message_id=len(self.requests),
                date=datetime.now(),
                chat=Chat(id=USER_ID, type="private"),
                text=getattr(method, "text", None),
            )
        return True

    async def stream_content(self, *args, **kwargs) -> AsyncGenerator[bytes, None]:
        yield b""

    async def close(self) -> None:
        pass


@pytest.fixture(scope="session")
def dispatcher() -> Dispatcher:
    # роутер можно подключить только к одному диспетчеру, поэтому он общий на все тесты
    dp = Dispatcher()
    dp.include_router(router)
    return dp


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[Database, None]:
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def config() -> Config:
    return Config(
        bot_token="42:TEST",
        db_path=":memory:",
        timezone=ZoneInfo("Europe/Moscow"),
        check_interval=1,
    )


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


_user = User(id=USER_ID, is_bot=False, first_name="Тест")
_chat = Chat(id=USER_ID, type="private")


def message_update(text: str, update_id: int = 1) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id, date=datetime.now(), chat=_chat, from_user=_user, text=text
        ),
    )


def callback_update(data: str, update_id: int = 1) -> Update:
    message = Message(message_id=999, date=datetime.now(), chat=_chat, text="card")
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id), from_user=_user, chat_instance="ci", message=message, data=data
        ),
    )
