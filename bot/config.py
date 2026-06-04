"""Конфигурация бота. Читает значения из .env"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

STORAGE_DIR = BASE_DIR / "storage"
TMP_DIR = STORAGE_DIR / "tmp"
DB_PATH = STORAGE_DIR / "db" / "bot.sqlite3"
TMP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Config:
    bot_token: str
    bot_username: str
    ffmpeg_bin: str
    ffprobe_bin: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    username = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    if not username:
        raise RuntimeError("BOT_USERNAME не задан в .env")
    return Config(
        bot_token=token,
        bot_username=username,
        ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg").strip(),
        ffprobe_bin=os.getenv("FFPROBE_BIN", "ffprobe").strip(),
    )


config = load_config() if os.getenv("BOT_TOKEN") else None
