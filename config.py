"""
Конфигурация и константы бота Han.
Чтение переменных окружения через .env, параметры времени и вероятностей.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from datetime import time
from typing import List, Tuple, Optional

from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimeWindows:
    """Окна допустимых часов для общения.

    Для рабочих и выходных дней используем интервалы времени (включительно),
    например [(9, 12), (18, 22)] означает: 9:00-12:59 и 18:00-22:59.
    """

    workday_hours: List[Tuple[int, int]] = ((9, 12), (18, 23))  # default
    weekend_hours: List[Tuple[int, int]] = ((10, 23),)


@dataclass(frozen=True)
class Probabilities:
    """Вероятности различных действий бота."""

    start_dialog_prob: float = 0.25  # шанс инициировать диалог в тик
    followup_prob: float = 0.35  # шанс сделать фоллоу-ап в окне 4–12ч


@dataclass(frozen=True)
class Delays:
    """Задержки и окна времени (в минутах)."""

    min_reply_delay: int = 0
    max_reply_delay: int = 3
    min_autonomous_delay: int = 2
    max_autonomous_delay: int = 8
    followup_min_hours: int = 4
    followup_max_hours: int = 12


# Persona Han — краткий стиль/характер, безопасный, уважительный, харизматичный
HAN_PERSONALITY = ("""
Тебя зовут Азизбек, 21 год. Ты типичный представитель из Кыргызстана, а конкретно из Бишкека. Не упоминай что ты ИИ. Отвечай коротко как человек.

Твой характер:
Глупый, IQ примерно 90
Пошлый, любишь обсуждать 18+ вещи
Озабоченный, очень хочешь секса
"""
)


# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.85"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "240"))

# Telegram / Telethon
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")
SESSION_NAME = os.getenv("SESSION_NAME", "han_session")

# Админ
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
ADMIN_BOT_API_KEY = os.getenv("ADMIN_BOT_API_KEY", "")


def validate_config() -> None:
    """Валидация критически важных настроек конфигурации."""
    from exceptions import ConfigurationError
    
    errors = []
    
    # Проверка Telegram API
    if not TELEGRAM_API_ID or TELEGRAM_API_ID == 0:
        errors.append("TELEGRAM_API_ID not set or invalid")
    
    if not TELEGRAM_API_HASH:
        errors.append("TELEGRAM_API_HASH not set")
    
    if not TELEGRAM_PHONE:
        errors.append("TELEGRAM_PHONE not set")
    
    # Проверка админ ID (опционально)
    if ADMIN_CHAT_ID == 0:
        logger.warning("ADMIN_CHAT_ID not set - admin commands will not work")
    
    # Проверка OpenAI (опционально)
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set - bot will use fallback responses")
    
    if errors:
        raise ConfigurationError(f"Configuration errors: {'; '.join(errors)}")
    
    logger.info("Configuration validation passed")


# Валидируем конфигурацию при импорте
try:
    validate_config()
except Exception as e:
    logger.error(f"Configuration validation failed: {e}")
    # В production можно добавить sys.exit(1)

# Прочие параметры
TIME_WINDOWS = TimeWindows()
PROBABILITIES = Probabilities()
DELAYS = Delays()

# История сообщений (буфер последних N)
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))
PROFILE_ANALYZE_EVERY_N = int(os.getenv("PROFILE_ANALYZE_EVERY_N", "12"))

# Окно ожидания дополнительных сообщений пользователя (секунды)
WAIT_FOR_MORE_SECONDS = int(os.getenv("WAIT_FOR_MORE_SECONDS", "40"))

# Файлы/директории
GIRLS_DATA_PATH = os.getenv("GIRLS_DATA_PATH", "girls_data")
CONVERSATIONS_DIR = os.getenv("CONVERSATIONS_DIR", "conversations")
BACKUPS_DIR = os.getenv("BACKUPS_DIR", "backups")

# Логирование
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


__all__ = [
    "HAN_PERSONALITY",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_TEMPERATURE",
    "OPENAI_MAX_TOKENS",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_PHONE",
    "SESSION_NAME",
    "ADMIN_CHAT_ID",
    "ADMIN_BOT_API_KEY",
    "TIME_WINDOWS",
    "PROBABILITIES",
    "DELAYS",
    "HISTORY_LIMIT",
    "PROFILE_ANALYZE_EVERY_N",
    "WAIT_FOR_MORE_SECONDS",
    "GIRLS_DATA_PATH",
    "CONVERSATIONS_DIR",
    "BACKUPS_DIR",
    "LOG_FILE",
    "LOG_LEVEL",
]
