"""
Система мониторинга и метрик для бота Han.
Отслеживание производительности, ошибок и состояния системы.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiofiles

logger = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    """Системные метрики бота."""
    start_time: float = field(default_factory=time.time)
    messages_received: int = 0
    messages_sent: int = 0
    api_requests: int = 0
    api_failures: int = 0
    errors_count: int = 0
    active_chats: int = 0
    
    # Производительность
    avg_response_time: float = 0.0
    memory_usage_mb: float = 0.0
    
    # Состояние соединений
    telegram_connected: bool = False
    openai_available: bool = False
    
    @property
    def uptime_seconds(self) -> float:
        """Время работы в секундах."""
        return time.time() - self.start_time
    
    @property 
    def uptime_formatted(self) -> str:
        """Форматированное время работы."""
        uptime = self.uptime_seconds
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    @property
    def success_rate(self) -> float:
        """Процент успешных API запросов."""
        total = self.api_requests
        if total == 0:
            return 100.0
        return ((total - self.api_failures) / total) * 100


class MetricsCollector:
    """Сборщик и хранилище метрик."""
    
    def __init__(self, metrics_file: str = "metrics.json"):
        self.metrics = SystemMetrics()
        self.metrics_file = Path(metrics_file)
        self._lock = asyncio.Lock()
        self._history: List[Dict[str, Any]] = []
        self._last_save = time.time()
        self._save_interval = 300  # 5 минут
        
    def increment_messages_received(self) -> None:
        """Увеличить счётчик полученных сообщений."""
        self.metrics.messages_received += 1
        
    def increment_messages_sent(self) -> None:
        """Увеличить счётчик отправленных сообщений."""
        self.metrics.messages_sent += 1
        
    def increment_api_requests(self) -> None:
        """Увеличить счётчик API запросов."""
        self.metrics.api_requests += 1
        
    def increment_api_failures(self) -> None:
        """Увеличить счётчик неудачных API запросов."""
        self.metrics.api_failures += 1
        
    def increment_errors(self) -> None:
        """Увеличить счётчик ошибок."""
        self.metrics.errors_count += 1
        
    def update_active_chats(self, count: int) -> None:
        """Обновить количество активных чатов."""
        self.metrics.active_chats = count
        
    def update_response_time(self, response_time: float) -> None:
        """Обновить среднее время ответа."""
        # Экспоненциальное скользящее среднее
        alpha = 0.1
        self.metrics.avg_response_time = (
            alpha * response_time + (1 - alpha) * self.metrics.avg_response_time
        )
        
    def update_memory_usage(self, memory_mb: float) -> None:
        """Обновить использование памяти."""
        self.metrics.memory_usage_mb = memory_mb
        
    def set_telegram_status(self, connected: bool) -> None:
        """Обновить статус соединения с Telegram."""
        self.metrics.telegram_connected = connected
        
    def set_openai_status(self, available: bool) -> None:
        """Обновить статус доступности OpenAI."""
        self.metrics.openai_available = available
        
    def get_metrics(self) -> SystemMetrics:
        """Получить текущие метрики."""
        return self.metrics
        
    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку метрик."""
        return {
            "uptime": self.metrics.uptime_formatted,
            "messages": {
                "received": self.metrics.messages_received,
                "sent": self.metrics.messages_sent,
                "ratio": (
                    self.metrics.messages_sent / max(self.metrics.messages_received, 1)
                )
            },
            "api": {
                "requests": self.metrics.api_requests,
                "failures": self.metrics.api_failures,
                "success_rate": f"{self.metrics.success_rate:.1f}%"
            },
            "performance": {
                "avg_response_time": f"{self.metrics.avg_response_time:.2f}s",
                "memory_usage": f"{self.metrics.memory_usage_mb:.1f}MB",
                "active_chats": self.metrics.active_chats
            },
            "status": {
                "telegram": "🟢" if self.metrics.telegram_connected else "🔴",
                "openai": "🟢" if self.metrics.openai_available else "🔴"
            },
            "errors": self.metrics.errors_count
        }
        
    async def save_metrics(self, force: bool = False) -> None:
        """Сохранить метрики в файл."""
        now = time.time()
        if not force and (now - self._last_save) < self._save_interval:
            return
            
        async with self._lock:
            try:
                # Добавляем снимок в историю
                snapshot = {
                    "timestamp": datetime.now().isoformat(),
                    "metrics": asdict(self.metrics)
                }
                self._history.append(snapshot)
                
                # Ограничиваем историю (последние 288 записей = 24 часа при интервале 5 мин)
                if len(self._history) > 288:
                    self._history = self._history[-288:]
                
                # Сохраняем в файл
                data = {
                    "current": asdict(self.metrics),
                    "history": self._history
                }
                
                async with aiofiles.open(self.metrics_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(data, ensure_ascii=False, indent=2))
                
                self._last_save = now
                logger.debug(f"Метрики сохранены в {self.metrics_file}")
                
            except Exception as e:
                logger.error(f"Ошибка сохранения метрик: {e}")
                
    async def load_metrics(self) -> None:
        """Загрузить метрики из файла."""
        if not self.metrics_file.exists():
            return
            
        try:
            async with aiofiles.open(self.metrics_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
                
            if "history" in data:
                self._history = data["history"]
                
            logger.info(f"Метрики загружены из {self.metrics_file}")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки метрик: {e}")
            
    def get_memory_usage(self) -> float:
        """Получить текущее использование памяти в МБ."""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0
        except Exception as e:
            logger.error(f"Ошибка получения использования памяти: {e}")
            return 0.0
            
    async def start_monitoring(self) -> None:
        """Запуск фонового мониторинга."""
        while True:
            try:
                # Обновляем использование памяти
                memory_usage = self.get_memory_usage()
                self.update_memory_usage(memory_usage)
                
                # Сохраняем метрики
                await self.save_metrics()
                
                # Ждём интервал
                await asyncio.sleep(self._save_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в мониторинге: {e}")
                await asyncio.sleep(60)  # Короткая пауза при ошибке


# Глобальный экземпляр коллектора метрик
metrics_collector = MetricsCollector()
