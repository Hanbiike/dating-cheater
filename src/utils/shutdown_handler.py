"""
Безопасная остановка: обработка SIGINT/SIGTERM и внешней команды.
"""
from __future__ import annotations

import asyncio
import logging
import signal

logger = logging.getLogger(__name__)


class Shutdown:
    """Грациозное завершение через asyncio.Event."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def install(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, self.request_stop)
            loop.add_signal_handler(signal.SIGTERM, self.request_stop)
        except NotImplementedError:
            # Windows и пр. — игнорируем
            pass

    def request_stop(self) -> None:
        if not self._event.is_set():
            logger.info("Получен сигнал на остановку")
            self._event.set()

    def is_stopping(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()
