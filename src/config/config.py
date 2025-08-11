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
try:
    TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
except ValueError:
    TELEGRAM_API_ID = 0
    
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")  # For bot API if needed
SESSION_NAME = os.getenv("SESSION_NAME", "han_session")

# Админ
try:
    ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or "0")
except ValueError:
    ADMIN_CHAT_ID = 0
ADMIN_BOT_API_KEY = os.getenv("ADMIN_BOT_API_KEY", "")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "")
DATABASE_HOST = os.getenv("DATABASE_HOST", "localhost")
DATABASE_PORT = int(os.getenv("DATABASE_PORT", "5432"))
DATABASE_NAME = os.getenv("DATABASE_NAME", "han_dating_bot")
DATABASE_USER = os.getenv("DATABASE_USER", "postgres")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "")
DATABASE_SSL_MODE = os.getenv("DATABASE_SSL_MODE", "prefer")

# Multi-bot Support
CURRENT_BOT_ID = os.getenv("CURRENT_BOT_ID", "")  # Will be set during migration
MULTI_BOT_ENABLED = os.getenv("MULTI_BOT_ENABLED", "false").lower() == "true"


def validate_config() -> None:
    """Валидация критически важных настроек конфигурации."""
    from src.utils.exceptions import ConfigurationError
    
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
    
    # Проверка Database (если включена поддержка мульти-бота)
    if MULTI_BOT_ENABLED:
        if not DATABASE_URL and not all([DATABASE_HOST, DATABASE_NAME, DATABASE_USER]):
            errors.append("Database configuration incomplete for multi-bot mode")
        
        if not CURRENT_BOT_ID:
            logger.warning("CURRENT_BOT_ID not set - will be generated during migration")
    
    if errors:
        raise ConfigurationError(f"Configuration errors: {'; '.join(errors)}")
    
    logger.info("Configuration validation passed")


def get_database_url() -> str:
    """Получить URL для подключения к базе данных."""
    if DATABASE_URL:
        return DATABASE_URL
    
    # Собрать URL из компонентов
    password_part = f":{DATABASE_PASSWORD}" if DATABASE_PASSWORD else ""
    return f"postgresql://{DATABASE_USER}{password_part}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}?sslmode={DATABASE_SSL_MODE}"


@dataclass(frozen=True)
class TelegramConfig:
    """Конфигурация Telegram."""
    
    bot_token: str
    api_id: int
    api_hash: str
    phone: str
    session_name: str
    
    @classmethod
    def from_env(cls) -> TelegramConfig:
        """Создать конфигурацию из переменных окружения."""
        return cls(
            bot_token=TELEGRAM_BOT_TOKEN,  # Default bot token
            api_id=TELEGRAM_API_ID,
            api_hash=TELEGRAM_API_HASH,
            phone=TELEGRAM_PHONE,
            session_name=SESSION_NAME
        )


@dataclass(frozen=True)
class Config:
    """Основная конфигурация приложения."""
    
    telegram: TelegramConfig
    database: DatabaseConfig
    time_windows: TimeWindows
    probabilities: Probabilities
    delays: Delays
    
    # OpenAI
    openai_api_key: str
    openai_model: str
    openai_temperature: float
    openai_max_tokens: int
    
    # Admin
    admin_chat_id: int
    admin_bot_api_key: str
    
    # Multi-bot settings
    multi_bot_enabled: bool
    current_bot_id: str
    
    # Paths
    girls_data_path: str
    conversations_dir: str
    backups_dir: str
    
    # Logging
    log_file: str
    log_level: str
    
    # Limits
    history_limit: int
    profile_analyze_every_n: int
    wait_for_more_seconds: int
    
    @classmethod
    def from_env(cls) -> Config:
        """Создать конфигурацию из переменных окружения."""
        return cls(
            telegram=TelegramConfig.from_env(),
            database=DatabaseConfig.from_env(),
            time_windows=TIME_WINDOWS,
            probabilities=PROBABILITIES,
            delays=DELAYS,
            openai_api_key=OPENAI_API_KEY,
            openai_model=OPENAI_MODEL,
            openai_temperature=OPENAI_TEMPERATURE,
            openai_max_tokens=OPENAI_MAX_TOKENS,
            admin_chat_id=ADMIN_CHAT_ID,
            admin_bot_api_key=ADMIN_BOT_API_KEY,
            multi_bot_enabled=MULTI_BOT_ENABLED,
            current_bot_id=CURRENT_BOT_ID,
            girls_data_path=GIRLS_DATA_PATH,
            conversations_dir=CONVERSATIONS_DIR,
            backups_dir=BACKUPS_DIR,
            log_file=LOG_FILE,
            log_level=LOG_LEVEL,
            history_limit=HISTORY_LIMIT,
            profile_analyze_every_n=PROFILE_ANALYZE_EVERY_N,
            wait_for_more_seconds=WAIT_FOR_MORE_SECONDS
        )


@dataclass(frozen=True)
class DatabaseConfig:
    """Конфигурация базы данных."""
    
    url: str
    host: str
    port: int
    name: str
    user: str
    password: str
    ssl_mode: str
    multi_bot_enabled: bool
    current_bot_id: str
    
    @classmethod
    def from_env(cls) -> DatabaseConfig:
        """Создать конфигурацию из переменных окружения."""
        return cls(
            url=get_database_url(),
            host=DATABASE_HOST,
            port=DATABASE_PORT,
            name=DATABASE_NAME,
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            ssl_mode=DATABASE_SSL_MODE,
            multi_bot_enabled=MULTI_BOT_ENABLED,
            current_bot_id=CURRENT_BOT_ID
        )


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
    "TELEGRAM_BOT_TOKEN",
    "SESSION_NAME",
    "ADMIN_CHAT_ID",
    "ADMIN_BOT_API_KEY",
    "DATABASE_URL",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "DATABASE_SSL_MODE",
    "CURRENT_BOT_ID",
    "MULTI_BOT_ENABLED",
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
    "get_database_url",
    "DatabaseConfig",
    "TelegramConfig",
    "Config",
]
