"""Точка входа. Запуск: python main.py"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import load_config
from bot.handlers import newpack, shared, start, manage
from bot.services.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

BOT_COMMANDS = [
    BotCommand(command="start",    description="Показать главное меню"),
    BotCommand(command="help",     description="Справка по боту"),
    BotCommand(command="settings", description="Настройки размера стикера"),
]


async def main() -> None:
    config = load_config()
    await init_db()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(shared.router)   # deep-link join первым
    dp.include_router(start.router)
    dp.include_router(manage.router)
    dp.include_router(newpack.router)

    # Регистрируем команды — они появятся в меню с 3 полосками
    await bot.set_my_commands(BOT_COMMANDS)

    logging.info("Bot @%s запущен", config.bot_username)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Остановлено")
