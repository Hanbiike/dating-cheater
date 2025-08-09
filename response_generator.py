"""
Генератор ответов Han через OpenAI Async SDK.

Эта версия использует последнюю версию официальной библиотеки `openai`
и её Responses API вместо устаревшего Chat Completions API. Responses API
позволяет явно задавать системные инструкции (instructions) и список
входных сообщений (input). История сообщений хранится по chat_id
и ограничивается значением HISTORY_LIMIT.
"""

from __future__ import annotations

import logging
import asyncio
import time
from typing import Any, Dict, List, Tuple, Optional
from dataclasses import dataclass, field

from openai import AsyncOpenAI
from girls_manager import GirlsManager
from exceptions import OpenAIError, ValidationError, safe_execute
from validators import Validator

from config import (
    HAN_PERSONALITY,
    HISTORY_LIMIT,
    OPENAI_API_KEY,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
)

logger = logging.getLogger(__name__)


@dataclass
class GenerationMetrics:
    """Метрики генерации для мониторинга."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    fallback_responses: int = 0
    total_response_time: float = 0.0
    
    @property
    def avg_response_time(self) -> float:
        """Среднее время ответа."""
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time / self.successful_requests
    
    @property 
    def success_rate(self) -> float:
        """Процент успешных запросов."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

class ResponseGenerator:
    """Асинхронная обёртка для генерации ответов с мониторингом и устойчивостью к ошибкам."""

    def __init__(self, girls_manager: Optional[GirlsManager] = None) -> None:
        """
        Инициализация генератора ответов.
        
        Args:
            girls_manager: Менеджер данных пользователей
        """
        self._client: AsyncOpenAI | None = None
        self._history: Dict[int, List[Tuple[str, str]]] = {}
        self._girls: Optional[GirlsManager] = girls_manager
        self._last_response_id: Dict[int, str] = {}
        self._metrics = GenerationMetrics()
        self._rate_limiter = asyncio.Semaphore(5)  # Макс 5 параллельных запросов
        
        # Инициализация клиента с проверкой ключа
        if OPENAI_API_KEY:
            try:
                Validator.validate_api_key(OPENAI_API_KEY)
                self._client = AsyncOpenAI(api_key=OPENAI_API_KEY)
                logger.info("OpenAI client initialized successfully")
            except ValidationError as e:
                logger.error(f"Invalid OpenAI API key format: {e}")
                self._client = None
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self._client = None
        else:
            logger.warning("OPENAI_API_KEY пуст — генерация будет отдавать фолбэки")
            self._client = None

    def add_to_history(self, chat_id: int, role: str, content: str) -> None:
        """Добавление сообщения в историю с валидацией."""
        try:
            chat_id = Validator.validate_chat_id(chat_id)
            content = Validator.validate_message_text(content)
            
            if role not in ['user', 'assistant']:
                raise ValidationError(f"Invalid role: {role}")
                
            buf = self._history.setdefault(chat_id, [])
            buf.append((role, content))
            
            if len(buf) > HISTORY_LIMIT:
                self._history[chat_id] = buf[-HISTORY_LIMIT:]
                
        except Exception as e:
            logger.error(f"Error adding to history for {chat_id}: {e}")

    def get_recent_history(self, chat_id: int) -> List[Dict[str, str]]:
        """Возвращает историю сообщений без системного сообщения."""
        try:
            chat_id = Validator.validate_chat_id(chat_id)
            buf = self._history.get(chat_id, [])
            return [{"role": r, "content": c} for r, c in buf[-HISTORY_LIMIT:]]
        except Exception as e:
            logger.error(f"Error getting history for {chat_id}: {e}")
            return []
    
    def get_metrics(self) -> GenerationMetrics:
        """Получение метрик производительности."""
        return self._metrics
    
    def reset_metrics(self) -> None:
        """Сброс метрик."""
        self._metrics = GenerationMetrics()

    async def generate(
        self,
        chat_id: int,
        user_message: str,
        profile_context: str,
        focus_topic: str,
        summary_text: str | None = None,
        system_goal: str | None = None,
    ) -> str:
        """Сгенерировать ответ Han, используя Responses API с previous_response_id по умолчанию."""
        start_time = time.time()
        self._metrics.total_requests += 1
        
        try:
            # Валидация входных данных
            chat_id = Validator.validate_chat_id(chat_id)
            user_message = Validator.validate_message_text(user_message)
            
            # Добавляем сообщение пользователя в историю
            self.add_to_history(chat_id, "user", user_message)

            # Формируем системные инструкции
            system_parts = [HAN_PERSONALITY]
            if profile_context:
                system_parts.append(f"Профиль собеседницы: {profile_context}")
            if focus_topic:
                system_parts.append(f"Сфокусируйся на теме: {focus_topic}")
            if summary_text:
                system_parts.append(f"Сводка: {summary_text}")
            if system_goal:
                system_parts.append(f"Цель: {system_goal}")
            instructions = "\n".join(system_parts)

            # Получаем историю сообщений
            messages = self.get_recent_history(chat_id)

            # Возврат фолбэка при отсутствии клиента
            if not self._client:
                logger.warning("OpenAI клиент не инициализирован. Возвращаем фолбэк-ответ.")
                text = self._get_fallback_response()
                self.add_to_history(chat_id, "assistant", text)
                self._metrics.fallback_responses += 1
                return text

            # Ограничение параллельных запросов
            async with self._rate_limiter:
                return await self._make_api_request(
                    chat_id, instructions, messages, start_time
                )
                
        except Exception as e:
            self._metrics.failed_requests += 1
            logger.exception("Ошибка генерации ответа для chat_id %s: %s", chat_id, e)
            text = self._get_fallback_response()
            self.add_to_history(chat_id, "assistant", text)
            return text
    
    async def _make_api_request(
        self, 
        chat_id: int, 
        instructions: str, 
        messages: List[Dict[str, str]], 
        start_time: float
    ) -> str:
        """Выполнение запроса к OpenAI API."""
        try:
            # previous_response_id: если есть, отправляем только последнее пользовательское сообщение
            prev_id: Optional[str] = None
            if self._girls is not None:
                prev_id = await self._girls.get_previous_response_id(chat_id)
            else:
                prev_id = self._last_response_id.get(chat_id)

            input_payload = messages[-1:] if prev_id else messages
            params: Dict[str, Any] = {
                "model": OPENAI_MODEL,
                "instructions": instructions,
                "input": input_payload,
                #"reasoning": {"effort": "minimal"},
                #"text": {"verbosity": "low"},
                "max_output_tokens": OPENAI_MAX_TOKENS,
            }
            if prev_id:
                params["previous_response_id"] = prev_id
                
            resp = await self._client.responses.create(**params)

            # Читаем текст ответа
            text: str = (resp.output_text or "").strip()
            if not text:
                text = self._get_fallback_response()
                self._metrics.fallback_responses += 1
            else:
                # Сохраняем response_id
                resp_id = getattr(resp, "id", None)
                if isinstance(resp_id, str) and resp_id:
                    if self._girls is not None:
                        await self._girls.set_previous_response_id(chat_id, resp_id)
                    else:
                        self._last_response_id[chat_id] = resp_id
                        
                # Обновляем метрики
                self._metrics.successful_requests += 1
                self._metrics.total_response_time += time.time() - start_time

            self.add_to_history(chat_id, "assistant", text)
            return text
            
        except Exception as e:
            logger.exception("OpenAI API request failed: %s", e)
            raise OpenAIError(f"API request failed: {str(e)}")
    
    def _get_fallback_response(self) -> str:
        """Получение резервного ответа."""
        fallback_responses = [
            "Окей. Расскажи ещё немного о себе — что тебя сейчас вдохновляет?",
            "Как прошёл твой день?",
            "Интересно... А что ты думаешь об этом?",
            "Расскажи мне больше об этом.",
            "А какие у тебя планы на выходные?"
        ]
        import random
        return random.choice(fallback_responses)