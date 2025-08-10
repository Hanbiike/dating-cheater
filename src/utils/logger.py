"""
Асинхронное логирование для бота Han:
- Логи в stdout и файл bot.log
- Асинхронная запись диалогов по chat_id в conversations/<id>.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import aiofiles

from src.config.config import CONVERSATIONS_DIR, LOG_FILE, LOG_LEVEL


def setup_logging() -> None:
    """Настройка логирования: stdout + файл."""
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(level)

    # Удалим существующие хэндлеры, чтобы не дублировать при повторном запуске
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(fmt)

    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(level)
    fh.setFormatter(fmt)

    logger.addHandler(sh)
    logger.addHandler(fh)


def setup_logger(name: str) -> logging.Logger:
    """Создать логгер с заданным именем."""
    # Инициализируем общее логирование если еще не сделано
    if not logging.getLogger().handlers:
        setup_logging()
    
    return logging.getLogger(name)


async def append_conversation(chat_id: int, record: Dict[str, Any]) -> None:
    """Асинхронно дописать запись разговора в conversations/<chat_id>.json.

    Формат: список объектов JSON; при отсутствии файла — создаётся новый с массивом.
    """
    path = Path(CONVERSATIONS_DIR) / f"{chat_id}.json"
    # Создаём при необходимости директорию
    path.parent.mkdir(parents=True, exist_ok=True)

    # Читаем существующие данные
    data = []
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
            if content.strip():
                data = json.loads(content)
    except FileNotFoundError:
        data = []
    except Exception:
        # В случае повреждения — создаём новый массив с записью ниже
        data = []

    # Дополняем
    record_with_ts = {"ts": datetime.utcnow().isoformat() + "Z", **record}
    data.append(record_with_ts)

    # Пишем обратно
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
