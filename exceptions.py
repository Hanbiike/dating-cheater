"""
Кастомные исключения для бота Han.
Обеспечивает централизованную обработку ошибок и логирование.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class HanBotError(Exception):
    """Базовое исключение для всех ошибок бота."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class OpenAIError(HanBotError):
    """Ошибки взаимодействия с OpenAI API."""
    pass


class TelegramError(HanBotError):
    """Ошибки взаимодействия с Telegram API."""
    pass


class DataStorageError(HanBotError):
    """Ошибки работы с файловой системой и данными."""
    pass


class ConfigurationError(HanBotError):
    """Ошибки конфигурации."""
    pass


class ValidationError(HanBotError):
    """Ошибки валидации данных."""
    pass


def handle_exception(exc: Exception, context: str = "", **kwargs) -> None:
    """
    Централизованная обработка исключений с логированием.
    
    Args:
        exc: Исключение для обработки
        context: Контекст, где произошла ошибка
        **kwargs: Дополнительные данные для логирования
    """
    if isinstance(exc, HanBotError):
        logger.error(
            "HanBot error in %s: %s | Details: %s | Context: %s",
            context, exc.message, exc.details, kwargs
        )
    else:
        logger.exception(
            "Unexpected error in %s: %s | Context: %s",
            context, str(exc), kwargs
        )


def safe_execute(func_name: str):
    """
    Декоратор для безопасного выполнения функций с логированием ошибок.
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                handle_exception(e, func_name, args=args, kwargs=kwargs)
                return None
                
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_exception(e, func_name, args=args, kwargs=kwargs)
                return None
                
        return async_wrapper if hasattr(func, '__code__') and 'async' in str(func.__code__) else sync_wrapper
    return decorator
