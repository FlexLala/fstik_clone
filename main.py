"""Точка входа. Запуск: python main.py"""
import asyncio
import logging
import signal
import time
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import load_config, TMP_DIR
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

# Rate limiting: 10 сообщений в минуту на пользователя
RATE_LIMIT_MSG = 10
RATE_LIMIT_WINDOW = 60  # секунд
_rate_store: dict[int, list[float]] = {}


def _clean_tmp() -> None:
    """Автоочистка временных файлов старше 24 часов."""
    now = time.time()
    max_age = 24 * 60 * 60
    cleaned = 0
    if TMP_DIR.exists():
        for item in TMP_DIR.iterdir():
            try:
                if item.is_file() and now - item.stat().st_mtime > max_age:
                    item.unlink()
                    cleaned += 1
            except Exception:
                pass
    logging.info("Cleanup TMP: удалено %d файлов старше 24ч", cleaned)


def _is_rate_limited(user_id: int) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    user_timestamps = _rate_store.get(user_id, [])
    # Оставляем только те, что в окне
    user_timestamps = [t for t in user_timestamps if t > window_start]
    _rate_store[user_id] = user_timestamps
    if len(user_timestamps) >= RATE_LIMIT_MSG:
        return True
    user_timestamps.append(now)
    return False


async def main() -> None:
    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler(sig):
        logging.info("Получен сигнал %s, начинаем остановку...", sig.name)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _signal_handler(s))
        except NotImplementedError:
            pass  # Windows не поддерживает add_signal_handler для SIGINT

    config = load_config()
    await init_db()

    # Cleanup временных файлов при старте
    await asyncio.to_thread(_clean_tmp)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Rate limiting middleware
    @dp.message.middleware()
    async def rate_limit_middleware(handler, event, data):
        user_id = event.from_user.id if event.from_user else 0
        if user_id and _is_rate_limited(user_id):
            await event.answer("⏳ Слишком много сообщений. Подожди минутку.")
            return
        return await handler(event, data)

    @dp.callback_query.middleware()
    async def rate_limit_cb_middleware(handler, event, data):
        user_id = event.from_user.id if event.from_user else 0
        if user_id and _is_rate_limited(user_id):
            await event.answer("⏳ Слишком много действий. Подожди минутку.")
            return
        return await handler(event, data)

    dp.include_router(shared.router)   # deep-link join первым
    dp.include_router(start.router)
    dp.include_router(manage.router)
    dp.include_router(newpack.router)

    # Регистрируем команды — они появятся в меню с 3 полосками
    await bot.set_my_commands(BOT_COMMANDS)

    logging.info("Bot @%s запущен", config.bot_username)
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем polling и ждём сигнала остановки
    polling_task = asyncio.create_task(dp.start_polling(bot))
    await shutdown_event.wait()
    logging.info("Останавливаем polling...")
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()
    logging.info("Остановлено")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Остановлено")
