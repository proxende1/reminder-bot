import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import load_config
from bot.db import Database
from bot.handlers import router
from bot.scheduler import ReminderScheduler

COMMANDS = [
    BotCommand(command="list", description="Активные напоминания"),
    BotCommand(command="help", description="Как задать напоминание"),
]


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = load_config()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = ReminderScheduler(bot, db, config.timezone, config.check_interval)
    scheduler_task = asyncio.create_task(scheduler.run())
    try:
        await bot.set_my_commands(COMMANDS)
        await dp.start_polling(bot, db=db, config=config)
    finally:
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
