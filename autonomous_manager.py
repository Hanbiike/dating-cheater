"""
Фоновая автономная логика инициирования диалогов и фоллоу-апов.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, Optional

from config import DELAYS, PROBABILITIES, TIME_WINDOWS, ADMIN_CHAT_ID
from conversation_initiator import generate_starter
from girls_manager import GirlsManager
from response_generator import ResponseGenerator

logger = logging.getLogger(__name__)


def now_allowed_hours(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Mon..6=Sun
    windows = TIME_WINDOWS.workday_hours if weekday < 5 else TIME_WINDOWS.weekend_hours
    for start, end in windows:
        if start <= hour <= end:
            return True
    return False


class AutonomousManager:
    """Управляет периодическими проверками и автономными сообщениями."""

    def __init__(
        self,
        girls: GirlsManager,
        rg: ResponseGenerator,
        send_message: Callable[[int, str], Awaitable[None]],
        is_stopping: Callable[[], bool],
        send_typing: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> None:
        self._girls = girls
        self._rg = rg
        self._send_message = send_message
        self._is_stopping = is_stopping
        self._send_typing = send_typing
        self._last_sent: Dict[int, datetime] = {}

    async def start(self) -> None:
        """Запуск бесконечного цикла с периодом ~30 минут."""
        while not self._is_stopping():
            try:
                await self._tick()
            except Exception as e:
                logger.exception("Ошибка в автономном цикле: %s", e)
            # сон ~30 минут
            await asyncio.sleep(60 * 30)

    async def _tick(self) -> None:
        if not now_allowed_hours():
            logger.debug("Не в окне общения — пропуск тика")
            return
        girls = await self._girls.list_girls()
        if not girls:
            return
        for gp in girls:
            if self._is_stopping():
                return
            if gp.chat_id == ADMIN_CHAT_ID:
                continue
            # шанс инициировать
            if random.random() > PROBABILITIES.start_dialog_prob:
                continue
            # ограничение по интервалу — минимум 6 часов между инициациями
            last = self._last_sent.get(gp.chat_id)
            if last and (datetime.now() - last) < timedelta(hours=6):
                continue
            profile = await self._girls.get_profile_context(gp.chat_id)
            focus = await self._girls.suggest_focus_topic(gp.chat_id)
            starter = await generate_starter(self._rg, gp.chat_id, profile, focus)

            # случайная задержка перед отправкой
            delay = random.randint(DELAYS.min_autonomous_delay, DELAYS.max_autonomous_delay)
            logger.info("Автоинициация %s через %s мин", gp.chat_id, delay)
            # имитация набора перед отправкой
            if self._send_typing:
                await self._send_typing(gp.chat_id, delay * 60)
            else:
                await asyncio.sleep(delay * 60)
            if self._is_stopping():
                return
            await self._send_message(gp.chat_id, starter)
            self._last_sent[gp.chat_id] = datetime.now()

    async def plan_followup(self, chat_id: int) -> None:
        """Вероятностный фоллоу-ап в окне 4–12 ч."""
        if chat_id == ADMIN_CHAT_ID:
            return
        if random.random() > PROBABILITIES.followup_prob:
            return
        hours = random.randint(DELAYS.followup_min_hours, DELAYS.followup_max_hours)
        eta = hours * 3600
        logger.info("Планируем фоллоу-ап для %s через %s ч", chat_id, hours)
        await asyncio.sleep(eta)
        if self._is_stopping():
            return
        profile = await self._girls.get_profile_context(chat_id)
        focus = await self._girls.suggest_focus_topic(chat_id)
        text = await generate_starter(self._rg, chat_id, profile, focus)
        # небольшая имитация набора 10–25 сек
        if self._send_typing:
            await self._send_typing(chat_id, random.randint(10, 25))
        await self._send_message(chat_id, text)
