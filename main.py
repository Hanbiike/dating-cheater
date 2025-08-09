"""
Точка входа: Telethon клиент, обработка входящих, интеграция с OpenAI,
логирование, админ-команды, автономный режим и graceful shutdown.
Версия с улучшенной обработкой ошибок и мониторингом.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageTypingAction

from admin import Admin
from autonomous_manager import AutonomousManager
from config import (
    ADMIN_CHAT_ID,
    DELAYS,
    SESSION_NAME,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_PHONE,
    WAIT_FOR_MORE_SECONDS,
)
from girls_manager import GirlsManager
from logger import append_conversation, setup_logging
from response_generator import ResponseGenerator
from shutdown_handler import Shutdown
from exceptions import HanBotError, TelegramError, handle_exception
from validators import Validator

logger = logging.getLogger("main")


async def async_input(prompt: str = "") -> str:
    """Асинхронный input, чтобы не блокировать цикл (исп. только для 2FA)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def process_user_message(
    chat_id: int, text: str, name: str,
    girls: GirlsManager, rg: ResponseGenerator,
    pending_timers: Dict[int, asyncio.Task],
    series_buffer: Dict[int, List[str]],
    send_message: Callable, send_typing: Callable,
    autonomous: Optional[AutonomousManager],
    client: TelegramClient
) -> None:
    """Обработка обычного пользовательского сообщения."""
    start_time = time.time()
    
    try:
        # Обновление профиля
        await girls.ensure_girl(chat_id, name)
        await girls.update_last_activity(chat_id)
        await girls.update_profile(chat_id, text)

        # Накопление серии сообщений
        buf = series_buffer.setdefault(chat_id, [])
        buf.append(text)
        
        # Сброс предыдущего таймера
        prev_task = pending_timers.get(chat_id)
        if prev_task and not prev_task.done():
            prev_task.cancel()

        async def delayed_process():
            """Отложенная обработка серии сообщений."""
            try:
                await asyncio.sleep(WAIT_FOR_MORE_SECONDS)
                
                # Получение контекста
                profile_context = await girls.get_profile_context(chat_id)
                focus_topic = await girls.suggest_focus_topic(chat_id)
                latest_summary = await girls.get_latest_summary_text(chat_id)

                # Имитация набора
                delay = random.randint(DELAYS.min_reply_delay, DELAYS.max_reply_delay)
                await client.send_read_acknowledge(chat_id)
                await send_typing(chat_id, delay * 60)

                # Генерация ответа
                series_text = "\n".join(series_buffer.get(chat_id, []))
                reply = await rg.generate(
                    chat_id=chat_id,
                    user_message=series_text,
                    profile_context=profile_context,
                    focus_topic=focus_topic,
                    summary_text=latest_summary,
                )
                
                await send_message(chat_id, reply)

                # Очистка буфера
                series_buffer[chat_id] = []

                # Планирование follow-up
                if autonomous:
                    asyncio.create_task(autonomous.plan_followup(chat_id))

                # Анализ сообщений
                recent = rg.get_recent_history(chat_id)[-10:]
                summary_id = await girls.analyze_and_summarize(chat_id, recent)
                if summary_id:
                    logger.info("Сохранена сводка %s для %s", summary_id, chat_id)

                # Обновление метрик времени ответа
                response_time = time.time() - start_time
                from metrics import metrics_collector
                metrics_collector.update_response_time(response_time)

            except asyncio.CancelledError:
                pass
            except Exception as e:
                handle_exception(e, "delayed_process", chat_id=chat_id)

        # Запуск отложенной обработки
        pending_timers[chat_id] = asyncio.create_task(delayed_process())
        
    except Exception as e:
        handle_exception(e, "process_user_message", chat_id=chat_id)


async def run_backup_loop(girls: GirlsManager, shutdown: Shutdown) -> None:
    """Цикл периодических бэкапов."""
    while not shutdown.is_stopping():
        try:
            girls_list = await girls.list_girls()
            for g in girls_list:
                if shutdown.is_stopping():
                    break
                    
                # Загрузка истории диалога
                from pathlib import Path
                import json
                import aiofiles
                from config import CONVERSATIONS_DIR
                
                conv_file = Path(CONVERSATIONS_DIR) / f"{g.chat_id}.json"
                messages = []
                
                if conv_file.exists():
                    try:
                        async with aiofiles.open(conv_file, "r", encoding="utf-8") as f:
                            content = await f.read()
                            if content.strip():
                                messages = json.loads(content)
                    except Exception as e:
                        logger.error(f"Ошибка чтения диалога {g.chat_id}: {e}")
                        
                await girls.backup_daily_chat(g.chat_id, messages)
                
            logger.info(f"Бэкап выполнен для {len(girls_list)} профилей")
            
        except Exception as e:
            handle_exception(e, "backup_loop")
            
        # Ожидание 24 часа
        await asyncio.sleep(60 * 60 * 24)


async def main() -> None:
    """Главная функция с улучшенной обработкой ошибок и мониторингом."""
    setup_logging()
    logger.info("Запуск Han Dating Bot...")
    
    # Импорт метрик после настройки логирования
    from metrics import metrics_collector
    from connection_manager import ConnectionManager
    
    try:
        # Инициализация компонентов
        girls = GirlsManager()
        # Примечание: новый girls_manager больше не требует загрузки
        
        rg = ResponseGenerator(girls)
        shutdown = Shutdown()
        shutdown.install()
        
        # Инициализация метрик
        await metrics_collector.load_metrics()
        monitoring_task = asyncio.create_task(metrics_collector.start_monitoring())
        
        # Telethon клиент с менеджером соединений
        client = TelegramClient(SESSION_NAME, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        connection_manager = ConnectionManager(client, TELEGRAM_PHONE)
        
        # Кэширование сущностей и дебаунс
        entity_cache: Dict[int, Any] = {}
        pending_timers: Dict[int, asyncio.Task] = {}
        series_buffer: Dict[int, List[str]] = {}
        
        async def resolve_peer(chat_id: int):
            """Резолв peer с кэшированием."""
            if chat_id in entity_cache:
                return entity_cache[chat_id]
            try:
                ent = await client.get_input_entity(chat_id)
                entity_cache[chat_id] = ent
                return ent
            except Exception as e:
                logger.warning(f"Failed to resolve peer {chat_id}: {e}")
                return chat_id

        async def resolve_identity(query: str) -> str:
            """Резолв идентичности пользователя."""
            q = query.strip()
            try:
                if q.startswith('@') or 't.me/' in q:
                    # Username или ссылка
                    username = q.replace('@', '').replace('t.me/', '')
                    entity = await client.get_entity(username)
                elif q.startswith('+') or q.isdigit():
                    # Телефон или ID
                    entity = await client.get_entity(q)
                else:
                    return f"Неизвестный формат запроса: {q}"
                    
                user_type = "User" if hasattr(entity, 'phone') else "Chat"
                username_info = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else "no username"
                name = getattr(entity, 'first_name', '') or getattr(entity, 'title', 'No name')
                
                return f"type={user_type}; id={entity.id}; username={username_info}; name={name}"
                
            except Exception as e:
                return f"Ошибка поиска: {str(e)}"

        async def send_message(chat_id: int, text: str) -> None:
            """Отправка сообщения с обработкой ошибок."""
            try:
                chat_id = Validator.validate_chat_id(chat_id)
                text = Validator.validate_message_text(text)
                
                peer = await resolve_peer(chat_id)
                await client.send_message(peer, text)
                
                metrics_collector.increment_messages_sent()
                await append_conversation(chat_id, {"direction": "out", "text": text})
                logger.debug(f"Sent message to {chat_id}: {text[:50]}...")
                
            except Exception as e:
                handle_exception(e, "send_message", chat_id=chat_id, text_length=len(text))
                raise TelegramError(f"Failed to send message: {str(e)}")

        async def send_typing(chat_id: int, seconds: int) -> None:
            """Отправка индикатора набора."""
            try:
                peer = await resolve_peer(chat_id)
                await client(SetTypingRequest(peer, SendMessageTypingAction()))
                await asyncio.sleep(min(seconds, 60))  # Лимит 60 секунд
            except Exception as e:
                logger.debug(f"Failed to send typing indicator to {chat_id}: {e}")

        # Инициализация админки и автономного менеджера
        admin = Admin(girls, send_message, shutdown.request_stop, rg, resolve_identity)
        autonomous: Optional[AutonomousManager] = None

        # Подключение к Telegram
        async def password_prompt() -> str:
            return await async_input("Введите пароль 2FA: ")

        connected = await connection_manager.connect_with_retry(password_prompt)
        if not connected:
            logger.error("Не удалось подключиться к Telegram")
            return

        metrics_collector.set_telegram_status(True)
        metrics_collector.set_openai_status(bool(rg._client))
        logger.info("Успешное подключение к Telegram")

        # Обработчик входящих сообщений
        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            """Улучшенный обработчик входящих сообщений."""
            try:
                # Базовые проверки
                if not event.message or not event.message.message:
                    return
                    
                sender = event.sender
                if sender and getattr(sender, "bot", False):
                    return

                chat_id = event.sender_id
                text = event.message.message.strip()
                name = (getattr(sender, "first_name", None) or "").strip()

                # Кэширование entity
                try:
                    if event.input_sender:
                        entity_cache[chat_id] = event.input_sender
                except Exception:
                    pass

                # Валидация
                chat_id = Validator.validate_chat_id(chat_id)
                text = Validator.validate_message_text(text)
                name = Validator.validate_name(name)

                # Метрики и логирование
                metrics_collector.increment_messages_received()
                await append_conversation(chat_id, {"direction": "in", "text": text})
                logger.info(f"Message from {chat_id} ({name}): {text[:100]}...")

                # Обновление счётчика активных чатов
                girls_list = await girls.list_girls()
                metrics_collector.update_active_chats(len(girls_list))

                # Админ команды
                if await admin.handle_admin_command(chat_id, text):
                    return

                # Обработка обычного сообщения
                await process_user_message(
                    chat_id, text, name, girls, rg, 
                    pending_timers, series_buffer,
                    send_message, send_typing, autonomous, client
                )

            except Exception as e:
                metrics_collector.increment_errors()
                handle_exception(e, "message_handler", chat_id=chat_id if 'chat_id' in locals() else None)

        # Запуск автономного менеджера
        autonomous = AutonomousManager(
            girls=girls,
            rg=rg, 
            send_message=send_message,
            is_stopping=shutdown.is_stopping,
            send_typing=send_typing
        )

        # Запуск всех задач
        auto_task = asyncio.create_task(autonomous.start())
        client_task = asyncio.create_task(client.run_until_disconnected())
        backup_task = asyncio.create_task(run_backup_loop(girls, shutdown))
        
        # Ожидание завершения
        logger.info("Бот запущен и готов к работе")
        await shutdown.wait()
        
    except Exception as e:
        logger.exception("Критическая ошибка в main(): %s", e)
        raise
        
    finally:
        # Безопасное завершение
        logger.info("Завершение работы...")
        
        # Остановка мониторинга
        if 'monitoring_task' in locals():
            monitoring_task.cancel()
            
        # Сохранение метрик
        if 'metrics_collector' in locals():
            await metrics_collector.save_metrics(force=True)
            
        # Отключение от Telegram
        if 'connection_manager' in locals():
            await connection_manager.disconnect()
            
        logger.info("Завершение выполнено")


if __name__ == "__main__":
    asyncio.run(main())
