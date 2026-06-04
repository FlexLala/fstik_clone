"""
Глобальная очередь обработки медиа.

Зачем: ffmpeg прожорлив. Если много людей одновременно кинут видео,
сервер ляжет. Ограничиваем число ОДНОВРЕМЕННЫХ задач через Semaphore,
остальные ждут. Пользователю показываем, что он в очереди.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

# Сколько ffmpeg-задач крутим параллельно. Подбери под сервер:
# обычно (ядра - 1), но не больше 3-4, чтобы хватило ресурсов другим ботам.
MAX_CONCURRENT = 1


@dataclass
class MediaQueue:
    max_concurrent: int = MAX_CONCURRENT
    _sem: asyncio.Semaphore = field(init=False)
    _waiting: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._sem = asyncio.Semaphore(self.max_concurrent)

    @property
    def waiting(self) -> int:
        return self._waiting

    @property
    def busy(self) -> int:
        return self.max_concurrent - self._sem._value  # noqa: SLF001

    @property
    def has_free_slot(self) -> bool:
        return self._sem._value > 0  # noqa: SLF001

    async def run(self, coro_factory):
        """coro_factory: callable без аргументов, возвращающий awaitable.

        Фабрика, а не готовая корутина, чтобы тяжёлая работа стартовала
        только после получения слота в семафоре.
        """
        self._waiting += 1
        counted = True  # пока числимся в ожидании
        try:
            async with self._sem:
                self._waiting -= 1
                counted = False
                return await coro_factory()
        finally:
            if counted:
                self._waiting -= 1


media_queue = MediaQueue()
