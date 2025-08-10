"""
IPC Communication Manager - Inter-Process Communication

Система для обмена сообщениями между ProcessSupervisor и bot processes.
Поддерживает синхронную и асинхронную передачу сообщений, управление соединениями
и обработку ошибок связи.

Функции:
- Message passing между процессами
- Connection management
- Message queuing и delivery
- Error handling и retry logic
- Health monitoring для IPC каналов
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Any, Callable, List
import aiofiles
import aiofiles.os


class MessageType(Enum):
    """Типы IPC сообщений"""
    COMMAND = "command"
    RESPONSE = "response"
    EVENT = "event"
    HEARTBEAT = "heartbeat"
    SHUTDOWN = "shutdown"
    ERROR = "error"


class MessagePriority(Enum):
    """Приоритеты сообщений"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class IPCMessage:
    """Структура IPC сообщения"""
    message_id: str
    message_type: MessageType
    sender_id: str
    recipient_id: str
    command: str
    data: Dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: float = None
    timeout: float = 30.0
    reply_to: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict:
        """Конвертация в словарь для сериализации"""
        return {
            'message_id': self.message_id,
            'message_type': self.message_type.value,
            'sender_id': self.sender_id,
            'recipient_id': self.recipient_id,
            'command': self.command,
            'data': self.data,
            'priority': self.priority.value,
            'timestamp': self.timestamp,
            'timeout': self.timeout,
            'reply_to': self.reply_to
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'IPCMessage':
        """Создание из словаря"""
        return cls(
            message_id=data['message_id'],
            message_type=MessageType(data['message_type']),
            sender_id=data['sender_id'],
            recipient_id=data['recipient_id'],
            command=data['command'],
            data=data['data'],
            priority=MessagePriority(data['priority']),
            timestamp=data['timestamp'],
            timeout=data['timeout'],
            reply_to=data.get('reply_to')
        )


class IPCChannel:
    """IPC канал для связи с одним процессом"""
    
    def __init__(self, channel_id: str, base_path: Path):
        self.channel_id = channel_id
        self.base_path = base_path
        self.inbox_path = base_path / f"{channel_id}_inbox"
        self.outbox_path = base_path / f"{channel_id}_outbox"
        
        # Очереди сообщений
        self.incoming_queue: asyncio.Queue = asyncio.Queue()
        self.outgoing_queue: asyncio.Queue = asyncio.Queue()
        
        # Состояние канала
        self.is_active = False
        self.last_activity = time.time()
        self.message_count = 0
        self.error_count = 0
        
        # Обработчики
        self.message_handlers: Dict[str, Callable] = {}
        
    async def initialize(self):
        """Инициализация канала"""
        try:
            # Создание директорий для сообщений
            await aiofiles.os.makedirs(self.inbox_path, exist_ok=True)
            await aiofiles.os.makedirs(self.outbox_path, exist_ok=True)
            
            self.is_active = True
            self.last_activity = time.time()
            
        except Exception as e:
            raise Exception(f"Failed to initialize IPC channel {self.channel_id}: {e}")
    
    async def send_message(self, message: IPCMessage) -> bool:
        """Отправка сообщения в канал"""
        try:
            if not self.is_active:
                return False
            
            # Сериализация сообщения
            message_data = json.dumps(message.to_dict(), indent=2)
            
            # Запись в файл
            message_file = self.outbox_path / f"{message.message_id}.json"
            async with aiofiles.open(message_file, 'w') as f:
                await f.write(message_data)
            
            self.message_count += 1
            self.last_activity = time.time()
            
            return True
            
        except Exception as e:
            self.error_count += 1
            raise Exception(f"Failed to send message via channel {self.channel_id}: {e}")
    
    async def receive_messages(self) -> List[IPCMessage]:
        """Получение сообщений из канала"""
        messages = []
        
        try:
            if not self.is_active:
                return messages
            
            # Сканирование inbox
            if await aiofiles.os.path.exists(self.inbox_path):
                for file_path in self.inbox_path.iterdir():
                    if file_path.suffix == '.json':
                        try:
                            # Чтение сообщения
                            async with aiofiles.open(file_path, 'r') as f:
                                message_data = await f.read()
                            
                            # Парсинг
                            data = json.loads(message_data)
                            message = IPCMessage.from_dict(data)
                            
                            messages.append(message)
                            
                            # Удаление обработанного файла
                            await aiofiles.os.remove(file_path)
                            
                        except Exception as e:
                            # Ошибка обработки конкретного сообщения
                            logging.error(f"Error processing message file {file_path}: {e}")
                            # Перемещение в error directory
                            error_path = self.base_path / "errors" / file_path.name
                            await aiofiles.os.makedirs(error_path.parent, exist_ok=True)
                            await aiofiles.os.rename(file_path, error_path)
            
            if messages:
                self.last_activity = time.time()
            
            return messages
            
        except Exception as e:
            self.error_count += 1
            raise Exception(f"Failed to receive messages from channel {self.channel_id}: {e}")
    
    async def cleanup(self):
        """Очистка канала"""
        try:
            self.is_active = False
            
            # Очистка директорий (опционально)
            # В production лучше оставить для debugging
            
        except Exception as e:
            logging.error(f"Error cleaning up channel {self.channel_id}: {e}")
    
    def register_handler(self, command: str, handler: Callable):
        """Регистрация обработчика команд"""
        self.message_handlers[command] = handler
    
    async def handle_message(self, message: IPCMessage) -> Optional[IPCMessage]:
        """Обработка входящего сообщения"""
        try:
            handler = self.message_handlers.get(message.command)
            if handler:
                result = await handler(message)
                
                # Создание ответного сообщения если нужно
                if result is not None:
                    response = IPCMessage(
                        message_id=str(uuid.uuid4()),
                        message_type=MessageType.RESPONSE,
                        sender_id=self.channel_id,
                        recipient_id=message.sender_id,
                        command=f"{message.command}_response",
                        data=result,
                        reply_to=message.message_id
                    )
                    return response
            
            return None
            
        except Exception as e:
            # Создание error response
            error_response = IPCMessage(
                message_id=str(uuid.uuid4()),
                message_type=MessageType.ERROR,
                sender_id=self.channel_id,
                recipient_id=message.sender_id,
                command="error",
                data={'error': str(e), 'original_command': message.command},
                reply_to=message.message_id
            )
            return error_response


class IPCManager:
    """
    IPC Manager - центральная система управления межпроцессорным общением
    
    Функции:
    - Управление IPC каналами для всех bot processes
    - Message routing и delivery
    - Connection monitoring
    - Error handling и recovery
    - Message queuing и priority handling
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path(tempfile.gettempdir()) / "multibot_ipc"
        self.logger = logging.getLogger(__name__)
        
        # Управление каналами
        self.channels: Dict[str, IPCChannel] = {}
        self.pending_responses: Dict[str, asyncio.Future] = {}
        
        # Состояние системы
        self.is_running = False
        self.message_handlers: Dict[str, Callable] = {}
        
        # Задачи обработки
        self.processing_tasks: List[asyncio.Task] = []
        
        # Статистика
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'errors': 0,
            'active_channels': 0
        }
        
    async def start(self):
        """Запуск IPC Manager"""
        try:
            self.logger.info("Starting IPC Manager")
            
            # Создание базовой директории
            await aiofiles.os.makedirs(self.base_path, exist_ok=True)
            
            # Создание supervisor канала
            await self.create_channel("supervisor")
            
            self.is_running = True
            
            # Запуск задач обработки
            self.processing_tasks = [
                asyncio.create_task(self._message_processing_loop()),
                asyncio.create_task(self._heartbeat_loop()),
                asyncio.create_task(self._cleanup_loop())
            ]
            
            self.logger.info("IPC Manager started successfully")
            
        except Exception as e:
            self.logger.error(f"Error starting IPC Manager: {e}")
            raise
    
    async def stop(self):
        """Остановка IPC Manager"""
        try:
            self.logger.info("Stopping IPC Manager")
            self.is_running = False
            
            # Остановка задач
            for task in self.processing_tasks:
                task.cancel()
            
            if self.processing_tasks:
                await asyncio.gather(*self.processing_tasks, return_exceptions=True)
            
            # Закрытие каналов
            for channel in self.channels.values():
                await channel.cleanup()
            
            self.channels.clear()
            
            self.logger.info("IPC Manager stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping IPC Manager: {e}")
    
    async def create_channel(self, channel_id: str) -> IPCChannel:
        """Создание нового IPC канала"""
        try:
            if channel_id in self.channels:
                return self.channels[channel_id]
            
            channel = IPCChannel(channel_id, self.base_path)
            await channel.initialize()
            
            self.channels[channel_id] = channel
            self.stats['active_channels'] = len(self.channels)
            
            self.logger.info(f"Created IPC channel: {channel_id}")
            return channel
            
        except Exception as e:
            self.logger.error(f"Error creating channel {channel_id}: {e}")
            raise
    
    async def remove_channel(self, channel_id: str):
        """Удаление IPC канала"""
        try:
            if channel_id not in self.channels:
                return
            
            channel = self.channels[channel_id]
            await channel.cleanup()
            
            del self.channels[channel_id]
            self.stats['active_channels'] = len(self.channels)
            
            self.logger.info(f"Removed IPC channel: {channel_id}")
            
        except Exception as e:
            self.logger.error(f"Error removing channel {channel_id}: {e}")
    
    async def send_message(self, recipient_id: str, message_data: Dict) -> Optional[Dict]:
        """
        Отправка сообщения с ожиданием ответа
        
        Args:
            recipient_id: ID получателя
            message_data: Данные сообщения
            
        Returns:
            Dict: Ответ от получателя или None при ошибке
        """
        try:
            # Создание сообщения
            message = IPCMessage(
                message_id=str(uuid.uuid4()),
                message_type=MessageType.COMMAND,
                sender_id="supervisor",
                recipient_id=recipient_id,
                command=message_data.get('command', 'unknown'),
                data=message_data.get('data', {}),
                priority=MessagePriority(message_data.get('priority', MessagePriority.NORMAL.value)),
                timeout=message_data.get('timeout', 30.0)
            )
            
            # Проверка канала
            if recipient_id not in self.channels:
                await self.create_channel(recipient_id)
            
            channel = self.channels[recipient_id]
            
            # Создание Future для ответа
            response_future = asyncio.Future()
            self.pending_responses[message.message_id] = response_future
            
            # Отправка сообщения
            success = await channel.send_message(message)
            
            if not success:
                del self.pending_responses[message.message_id]
                return None
            
            self.stats['messages_sent'] += 1
            
            # Ожидание ответа
            try:
                response = await asyncio.wait_for(response_future, timeout=message.timeout)
                return response
            except asyncio.TimeoutError:
                self.logger.warning(f"Timeout waiting for response from {recipient_id}")
                return None
            finally:
                if message.message_id in self.pending_responses:
                    del self.pending_responses[message.message_id]
                
        except Exception as e:
            self.logger.error(f"Error sending message to {recipient_id}: {e}")
            self.stats['errors'] += 1
            return None
    
    async def broadcast_message(self, message_data: Dict, exclude: Optional[List[str]] = None):
        """Отправка сообщения всем каналам"""
        exclude = exclude or []
        
        tasks = []
        for channel_id in self.channels:
            if channel_id not in exclude:
                task = asyncio.create_task(self.send_message(channel_id, message_data))
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def process_messages(self):
        """Обработка входящих сообщений (для вызова извне)"""
        for channel in self.channels.values():
            try:
                messages = await channel.receive_messages()
                for message in messages:
                    await self._handle_incoming_message(message, channel)
                    
            except Exception as e:
                self.logger.error(f"Error processing messages from channel {channel.channel_id}: {e}")
    
    async def _message_processing_loop(self):
        """Основной цикл обработки сообщений"""
        while self.is_running:
            try:
                await self.process_messages()
                await asyncio.sleep(0.1)  # 100ms между проверками
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in message processing loop: {e}")
                await asyncio.sleep(1)
    
    async def _handle_incoming_message(self, message: IPCMessage, channel: IPCChannel):
        """Обработка входящего сообщения"""
        try:
            self.stats['messages_received'] += 1
            
            # Обработка ответов
            if message.message_type == MessageType.RESPONSE and message.reply_to:
                if message.reply_to in self.pending_responses:
                    future = self.pending_responses[message.reply_to]
                    if not future.done():
                        future.set_result(message.data)
                    return
            
            # Обработка команд
            response = await channel.handle_message(message)
            
            if response:
                # Отправка ответа
                await channel.send_message(response)
                
        except Exception as e:
            self.logger.error(f"Error handling message {message.message_id}: {e}")
            self.stats['errors'] += 1
    
    async def _heartbeat_loop(self):
        """Цикл отправки heartbeat сообщений"""
        while self.is_running:
            try:
                # Отправка heartbeat всем каналам
                heartbeat_data = {
                    'command': 'heartbeat',
                    'data': {
                        'timestamp': time.time(),
                        'supervisor_status': 'running'
                    }
                }
                
                await self.broadcast_message(heartbeat_data, exclude=['supervisor'])
                
                await asyncio.sleep(30)  # Heartbeat каждые 30 секунд
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(30)
    
    async def _cleanup_loop(self):
        """Цикл очистки старых файлов и неактивных каналов"""
        while self.is_running:
            try:
                current_time = time.time()
                
                # Проверка неактивных каналов
                inactive_channels = []
                for channel_id, channel in self.channels.items():
                    if channel_id != "supervisor":  # Не удаляем supervisor канал
                        if current_time - channel.last_activity > 300:  # 5 минут
                            inactive_channels.append(channel_id)
                
                # Удаление неактивных каналов
                for channel_id in inactive_channels:
                    self.logger.info(f"Removing inactive channel: {channel_id}")
                    await self.remove_channel(channel_id)
                
                # Очистка старых файлов ошибок
                error_dir = self.base_path / "errors"
                if await aiofiles.os.path.exists(error_dir):
                    for file_path in error_dir.iterdir():
                        if current_time - file_path.stat().st_mtime > 86400:  # 24 часа
                            await aiofiles.os.remove(file_path)
                
                await asyncio.sleep(300)  # Очистка каждые 5 минут
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(300)
    
    def register_handler(self, channel_id: str, command: str, handler: Callable):
        """Регистрация обработчика команд для канала"""
        if channel_id in self.channels:
            self.channels[channel_id].register_handler(command, handler)
    
    def get_stats(self) -> Dict:
        """Получение статистики IPC Manager"""
        return {
            **self.stats,
            'uptime': time.time() - (self.stats.get('start_time', time.time())),
            'channels': {
                channel_id: {
                    'message_count': channel.message_count,
                    'error_count': channel.error_count,
                    'last_activity': channel.last_activity,
                    'is_active': channel.is_active
                }
                for channel_id, channel in self.channels.items()
            }
        }
