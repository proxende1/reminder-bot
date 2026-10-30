import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    timezone: ZoneInfo
    check_interval: float


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env и впишите токен от @BotFather."
        )
    return Config(
        bot_token=token,
        db_path=os.getenv("DB_PATH", "data/reminders.db"),
        timezone=ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow")),
        check_interval=float(os.getenv("CHECK_INTERVAL", "10")),
    )
