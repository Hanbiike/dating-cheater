"""
Менеджер соединений для обеспечения устойчивости к сбоям.
Включает retry логику, health checks и мониторинг соединений.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass, field
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError, SessionPasswordNeededError
from src.utils.exceptions import TelegramError, handle_exception

logger = logging.getLogger(__name__)


@dataclass
class ConnectionMetrics:
    """Метрики состояния соединения."""
    connect_attempts: int = 0
    successful_connections: int = 0
    connection_failures: int = 0
    last_connection_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    is_connected: bool = False
    
    @property
    def uptime(self) -> float:
        """Время работы текущего соединения в секундах."""
        if not self.is_connected or not self.last_connection_time:
            return 0.0
        return time.time() - self.last_connection_time


class ConnectionManager:
    """Менеджер соединений с retry логикой и мониторингом."""
    
    def __init__(
        self,
        client: TelegramClient,
        phone: str,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        health_check_interval: float = 300.0  # 5 минут
    ):
        self.client = client
        self.phone = phone
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.health_check_interval = health_check_interval
        
        self.metrics = ConnectionMetrics()
        self._health_check_task: Optional[asyncio.Task] = None
        self._reconnect_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        
    async def connect_with_retry(self, password_callback: Optional[Callable[[], str]] = None) -> bool:
        """
        Подключение с retry логикой.
        
        Args:
            password_callback: Функция для получения 2FA пароля
            
        Returns:
            True если подключение успешно, False иначе
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                self.metrics.connect_attempts += 1
                logger.info(f"Попытка подключения {attempt}/{self.max_retries}")
                
                await self.client.start(phone=self.phone)
                
                # Успешное подключение
                self.metrics.successful_connections += 1
                self.metrics.last_connection_time = time.time()
                self.metrics.is_connected = True
                
                logger.info("Подключение к Telegram успешно")
                
                # Запускаем мониторинг здоровья соединения
                self._health_check_task = asyncio.create_task(self._health_check_loop())
                
                return True
                
            except SessionPasswordNeededError:
                if password_callback:
                    try:
                        password = password_callback()
                        await self.client.start(password=password)
                        
                        self.metrics.successful_connections += 1
                        self.metrics.last_connection_time = time.time()
                        self.metrics.is_connected = True
                        
                        logger.info("Подключение с 2FA успешно")
                        self._health_check_task = asyncio.create_task(self._health_check_loop())
                        return True
                        
                    except Exception as e:
                        logger.error(f"Ошибка 2FA аутентификации: {e}")
                        self.metrics.connection_failures += 1
                        self.metrics.last_failure_time = time.time()
                else:
                    logger.error("Требуется 2FA пароль, но callback не предоставлен")
                    self.metrics.connection_failures += 1
                    self.metrics.last_failure_time = time.time()
                    return False
                    
            except AuthKeyDuplicatedError:
                logger.warning("Дублированный auth key, пересоздаём сессию")
                await self._recreate_session()
                continue
                
            except FloodWaitError as e:
                wait_time = min(e.seconds, self.max_delay)
                logger.warning(f"FloodWait: ждём {wait_time} секунд")
                await asyncio.sleep(wait_time)
                continue
                
            except Exception as e:
                self.metrics.connection_failures += 1
                self.metrics.last_failure_time = time.time()
                
                handle_exception(e, "telegram_connection", attempt=attempt)
                
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
                    logger.info(f"Ждём {delay} секунд перед повторной попыткой")
                    await asyncio.sleep(delay)
                else:
                    logger.error("Исчерпаны попытки подключения")
                    
        self.metrics.is_connected = False
        return False
    
    async def _recreate_session(self) -> None:
        """Пересоздание сессии при дублированном auth key."""
        try:
            await self.client.disconnect()
            
            # Удаляем файлы сессии
            session_file = Path(f"{self.client.session.filename}.session")
            if session_file.exists():
                session_file.unlink()
                
            journal_file = Path(f"{self.client.session.filename}.session-journal")
            if journal_file.exists():
                journal_file.unlink()
                
            logger.info("Файлы сессии удалены для пересоздания")
            
        except Exception as e:
            logger.error(f"Ошибка при пересоздании сессии: {e}")
    
    async def _health_check_loop(self) -> None:
        """Периодическая проверка здоровья соединения."""
        while not self._shutdown_event.is_set() and self.metrics.is_connected:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                if self._shutdown_event.is_set():
                    break
                    
                # Простая проверка соединения
                await self.client.get_me()
                logger.debug("Health check passed")
                
            except Exception as e:
                logger.warning(f"Health check failed: {e}")
                self.metrics.is_connected = False
                self._reconnect_event.set()
                break
    
    async def disconnect(self) -> None:
        """Корректное отключение."""
        self._shutdown_event.set()
        self.metrics.is_connected = False
        
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        try:
            await self.client.disconnect()
            logger.info("Отключение от Telegram выполнено")
        except Exception as e:
            logger.error(f"Ошибка при отключении: {e}")
    
    def get_metrics(self) -> ConnectionMetrics:
        """Получение метрик соединения."""
        return self.metrics
    
    def is_healthy(self) -> bool:
        """Проверка здоровья соединения."""
        return self.metrics.is_connected and not self._shutdown_event.is_set()
