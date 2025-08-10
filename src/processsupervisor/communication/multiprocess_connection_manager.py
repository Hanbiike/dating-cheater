"""
Multi-Process Connection Manager - Enhanced Connection Management

Адаптация connection_manager.py для работы в multi-process ProcessSupervisor среде.
Поддерживает process-isolated connections, shared state management,
и координацию между bot processes.

Функции:
- Process-isolated connection management
- Shared connection state coordination
- Multi-process health monitoring
- Connection pooling и load balancing
- Cross-process connection recovery
- IPC-based connection coordination
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Set
import threading
import json

from telethon import TelegramClient
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError, SessionPasswordNeededError

from src.core.connection_manager import ConnectionManager as LegacyConnectionManager, ConnectionMetrics
from src.processsupervisor.communication.ipc_communication import IPCManager, IPCMessage, MessageType, MessagePriority
from src.utils.exceptions import TelegramError, handle_exception

# Phase 2C Integration: Database coordination imports
from src.database.integration import DatabaseIntegrationManager


class ConnectionState(Enum):
    """Состояния connection в multi-process среде"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    SUSPENDED = "suspended"


class ConnectionRole(Enum):
    """Роли connection в multi-process архитектуре"""
    PRIMARY = "primary"      # Основное соединение бота
    BACKUP = "backup"        # Резервное соединение
    SHARED = "shared"        # Разделяемое соединение
    ISOLATED = "isolated"    # Изолированное соединение


@dataclass
class ProcessConnectionInfo:
    """Информация о connection конкретного процесса"""
    process_id: str
    connection_id: str
    state: ConnectionState
    role: ConnectionRole
    created_at: float
    last_activity: float
    metrics: ConnectionMetrics = field(default_factory=ConnectionMetrics)
    session_file: Optional[Path] = None
    api_credentials: Dict[str, Any] = field(default_factory=dict)
    
    def update_activity(self):
        """Обновление времени последней активности"""
        self.last_activity = time.time()
    
    def is_active(self, timeout: float = 300.0) -> bool:
        """Проверка активности connection"""
        return time.time() - self.last_activity < timeout


@dataclass 
class ConnectionPool:
    """Пул connections для load balancing"""
    pool_id: str
    connections: Dict[str, ProcessConnectionInfo] = field(default_factory=dict)
    load_balancer_strategy: str = "round_robin"
    max_connections: int = 10
    current_index: int = 0
    
    def add_connection(self, connection_info: ProcessConnectionInfo):
        """Добавление connection в пул"""
        self.connections[connection_info.connection_id] = connection_info
    
    def remove_connection(self, connection_id: str):
        """Удаление connection из пула"""
        if connection_id in self.connections:
            del self.connections[connection_id]
    
    def get_next_connection(self) -> Optional[ProcessConnectionInfo]:
        """Получение следующего connection для load balancing"""
        active_connections = [
            conn for conn in self.connections.values()
            if conn.state == ConnectionState.CONNECTED and conn.is_active()
        ]
        
        if not active_connections:
            return None
        
        if self.load_balancer_strategy == "round_robin":
            connection = active_connections[self.current_index % len(active_connections)]
            self.current_index += 1
            return connection
        elif self.load_balancer_strategy == "least_active":
            return min(active_connections, key=lambda c: c.last_activity)
        else:
            return active_connections[0]


class MultiProcessConnectionManager:
    """
    Multi-Process Connection Manager - enhanced connection management для ProcessSupervisor
    
    Функции:
    - Process-isolated connection management
    - Cross-process connection coordination
    - Connection pooling и load balancing
    - Shared state management via IPC
    - Multi-process health monitoring
    """
    
    def __init__(self, process_id: str, ipc_manager: Optional[IPCManager] = None):
        self.process_id = process_id
        self.logger = logging.getLogger(__name__)
        
        # IPC для координации между процессами
        self.ipc_manager = ipc_manager
        
        # Phase 2C Integration: Database coordination
        self.db_integration = DatabaseIntegrationManager(bot_id=process_id)
        self._db_initialized = False
        
        # Local connection management
        self.connections: Dict[str, ProcessConnectionInfo] = {}
        self.legacy_managers: Dict[str, LegacyConnectionManager] = {}
        
        # Connection pools
        self.connection_pools: Dict[str, ConnectionPool] = {}
        
        # Shared state coordination
        self.shared_state_file = Path("shared_connections.json")
        self.state_lock = threading.Lock()
        
        # Monitoring
        self.monitoring_enabled = True
        self.monitoring_interval = 30.0
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Configuration
        self.max_connections_per_process = 5
        self.connection_timeout = 300.0
        self.recovery_enabled = True
        
        # Statistics
        self.stats = {
            'connections_created': 0,
            'connections_failed': 0,
            'recovery_attempts': 0,
            'successful_recoveries': 0,
            'ipc_messages_sent': 0,
            'ipc_messages_received': 0
        }
    
    async def start(self):
        """Запуск Multi-Process Connection Manager"""
        try:
            self.logger.info(f"Starting Multi-Process Connection Manager for process {self.process_id}")
            
            # Phase 2C Integration: Initialize database coordination
            if not self._db_initialized:
                db_success = await self.db_integration.initialize(enable_migration=True)
                if db_success:
                    self._db_initialized = True
                    self.logger.info("✅ Database integration initialized for connection manager")
                else:
                    self.logger.warning("⚠️ Database integration failed, using fallback mode")
            
            # Загрузка shared state
            await self._load_shared_state()
            
            # Регистрация IPC handlers
            if self.ipc_manager:
                await self._register_ipc_handlers()
            
            # Запуск мониторинга
            if self.monitoring_enabled:
                self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            self.logger.info("Multi-Process Connection Manager started successfully")
            
        except Exception as e:
            self.logger.error(f"Error starting Multi-Process Connection Manager: {e}")
            raise
    
    async def stop(self):
        """Остановка Multi-Process Connection Manager"""
        try:
            self.logger.info("Stopping Multi-Process Connection Manager")
            
            # Остановка мониторинга
            if self.monitoring_task:
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    pass
            
            # Graceful shutdown всех connections
            for connection_info in self.connections.values():
                await self._disconnect_connection(connection_info.connection_id)
            
            # Phase 2C Integration: Shutdown database coordination
            if self._db_initialized:
                await self.db_integration.shutdown()
                self._db_initialized = False
                self.logger.info("✅ Database integration shutdown complete")
            
            # Сохранение shared state
            await self._save_shared_state()
            
            self.logger.info("Multi-Process Connection Manager stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Multi-Process Connection Manager: {e}")
    
    async def create_connection(self, bot_id: str, api_id: int, api_hash: str, 
                             phone: str, session_file: Optional[Path] = None,
                             role: ConnectionRole = ConnectionRole.PRIMARY) -> str:
        """Создание нового connection для бота"""
        try:
            connection_id = f"{self.process_id}_{bot_id}_{str(uuid.uuid4())[:8]}"
            
            # Проверка лимитов
            if len(self.connections) >= self.max_connections_per_process:
                raise Exception("Max connections per process exceeded")
            
            # Создание TelegramClient
            if session_file:
                session_path = session_file
            else:
                session_path = Path(f"sessions/{connection_id}.session")
                session_path.parent.mkdir(exist_ok=True)
            
            client = TelegramClient(str(session_path), api_id, api_hash)
            
            # Создание legacy connection manager
            legacy_manager = LegacyConnectionManager(
                client=client,
                phone=phone,
                max_retries=5,
                base_delay=1.0,
                max_delay=60.0
            )
            
            # Создание connection info
            connection_info = ProcessConnectionInfo(
                process_id=self.process_id,
                connection_id=connection_id,
                state=ConnectionState.DISCONNECTED,
                role=role,
                created_at=time.time(),
                last_activity=time.time(),
                session_file=session_path,
                api_credentials={
                    'api_id': api_id,
                    'api_hash': api_hash,
                    'phone': phone
                }
            )
            
            # Сохранение
            self.connections[connection_id] = connection_info
            self.legacy_managers[connection_id] = legacy_manager
            
            # Уведомление через IPC
            await self._notify_connection_created(connection_info)
            
            self.stats['connections_created'] += 1
            self.logger.info(f"Created connection {connection_id} for bot {bot_id}")
            
            return connection_id
            
        except Exception as e:
            self.logger.error(f"Error creating connection for bot {bot_id}: {e}")
            self.stats['connections_failed'] += 1
            raise
    
    async def connect(self, connection_id: str) -> bool:
        """Установка connection"""
        try:
            if connection_id not in self.connections:
                raise ValueError(f"Connection {connection_id} not found")
            
            connection_info = self.connections[connection_id]
            legacy_manager = self.legacy_managers[connection_id]
            
            # Обновление состояния
            connection_info.state = ConnectionState.CONNECTING
            await self._notify_connection_state_changed(connection_info)
            
            # Установка соединения через legacy manager
            success = await legacy_manager.connect()
            
            if success:
                connection_info.state = ConnectionState.CONNECTED
                connection_info.update_activity()
                connection_info.metrics.successful_connections += 1
                
                self.logger.info(f"Connection {connection_id} established successfully")
            else:
                connection_info.state = ConnectionState.FAILED
                connection_info.metrics.connection_failures += 1
                
                self.logger.error(f"Failed to establish connection {connection_id}")
            
            await self._notify_connection_state_changed(connection_info)
            return success
            
        except Exception as e:
            self.logger.error(f"Error connecting {connection_id}: {e}")
            if connection_id in self.connections:
                self.connections[connection_id].state = ConnectionState.FAILED
            return False
    
    async def disconnect(self, connection_id: str) -> bool:
        """Разрыв connection"""
        try:
            return await self._disconnect_connection(connection_id)
            
        except Exception as e:
            self.logger.error(f"Error disconnecting {connection_id}: {e}")
            return False
    
    async def _disconnect_connection(self, connection_id: str) -> bool:
        """Внутренняя функция разрыва connection"""
        if connection_id not in self.connections:
            return False
        
        connection_info = self.connections[connection_id]
        legacy_manager = self.legacy_managers[connection_id]
        
        # Graceful disconnect
        await legacy_manager.disconnect()
        
        connection_info.state = ConnectionState.DISCONNECTED
        await self._notify_connection_state_changed(connection_info)
        
        self.logger.info(f"Connection {connection_id} disconnected")
        return True
    
    async def get_connection(self, connection_id: str) -> Optional[TelegramClient]:
        """Получение TelegramClient для connection"""
        try:
            if connection_id not in self.connections:
                return None
            
            connection_info = self.connections[connection_id]
            
            if connection_info.state != ConnectionState.CONNECTED:
                return None
            
            legacy_manager = self.legacy_managers[connection_id]
            connection_info.update_activity()
            
            return legacy_manager.client
            
        except Exception as e:
            self.logger.error(f"Error getting connection {connection_id}: {e}")
            return None
    
    async def create_connection_pool(self, pool_id: str, max_connections: int = 10,
                                   strategy: str = "round_robin") -> ConnectionPool:
        """Создание пула connections"""
        pool = ConnectionPool(
            pool_id=pool_id,
            max_connections=max_connections,
            load_balancer_strategy=strategy
        )
        
        self.connection_pools[pool_id] = pool
        self.logger.info(f"Created connection pool {pool_id} with max {max_connections} connections")
        
        return pool
    
    async def add_connection_to_pool(self, pool_id: str, connection_id: str):
        """Добавление connection в пул"""
        if pool_id not in self.connection_pools:
            raise ValueError(f"Connection pool {pool_id} not found")
        
        if connection_id not in self.connections:
            raise ValueError(f"Connection {connection_id} not found")
        
        pool = self.connection_pools[pool_id]
        connection_info = self.connections[connection_id]
        
        pool.add_connection(connection_info)
        self.logger.info(f"Added connection {connection_id} to pool {pool_id}")
    
    async def get_pooled_connection(self, pool_id: str) -> Optional[str]:
        """Получение connection из пула"""
        if pool_id not in self.connection_pools:
            return None
        
        pool = self.connection_pools[pool_id]
        connection_info = pool.get_next_connection()
        
        if connection_info:
            connection_info.update_activity()
            return connection_info.connection_id
        
        return None
    
    async def _register_ipc_handlers(self):
        """Регистрация IPC handlers для координации"""
        if not self.ipc_manager:
            return
        
        # Handler для запросов состояния connections
        self.ipc_manager.register_handler(
            self.process_id,
            "get_connection_status",
            self._handle_get_connection_status
        )
        
        # Handler для coordination requests
        self.ipc_manager.register_handler(
            self.process_id,
            "coordinate_connection",
            self._handle_coordinate_connection
        )
        
        # Handler для health checks
        self.ipc_manager.register_handler(
            self.process_id,
            "connection_health_check",
            self._handle_connection_health_check
        )
    
    async def _handle_get_connection_status(self, message: IPCMessage) -> Dict[str, Any]:
        """Handler для запроса статуса connections"""
        try:
            connection_id = message.data.get('connection_id')
            
            if connection_id and connection_id in self.connections:
                connection_info = self.connections[connection_id]
                return {
                    'status': 'found',
                    'connection_info': {
                        'connection_id': connection_info.connection_id,
                        'state': connection_info.state.value,
                        'role': connection_info.role.value,
                        'last_activity': connection_info.last_activity,
                        'is_active': connection_info.is_active()
                    }
                }
            else:
                # Возврат всех connections процесса
                return {
                    'status': 'list',
                    'connections': {
                        cid: {
                            'state': info.state.value,
                            'role': info.role.value,
                            'last_activity': info.last_activity,
                            'is_active': info.is_active()
                        }
                        for cid, info in self.connections.items()
                    }
                }
                
        except Exception as e:
            self.logger.error(f"Error handling get_connection_status: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def _handle_coordinate_connection(self, message: IPCMessage) -> Dict[str, Any]:
        """Handler для coordination requests"""
        try:
            action = message.data.get('action')
            
            if action == 'suspend':
                # Приостановка connections для coordination
                connection_id = message.data.get('connection_id')
                if connection_id in self.connections:
                    self.connections[connection_id].state = ConnectionState.SUSPENDED
                    return {'status': 'suspended', 'connection_id': connection_id}
            
            elif action == 'resume':
                # Возобновление connections
                connection_id = message.data.get('connection_id')
                if connection_id in self.connections:
                    self.connections[connection_id].state = ConnectionState.CONNECTED
                    return {'status': 'resumed', 'connection_id': connection_id}
            
            return {'status': 'unknown_action', 'action': action}
            
        except Exception as e:
            self.logger.error(f"Error handling coordinate_connection: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def _handle_connection_health_check(self, message: IPCMessage) -> Dict[str, Any]:
        """Handler для health checks"""
        try:
            health_info = {}
            
            for connection_id, connection_info in self.connections.items():
                legacy_manager = self.legacy_managers.get(connection_id)
                
                health_info[connection_id] = {
                    'state': connection_info.state.value,
                    'is_active': connection_info.is_active(),
                    'last_activity': connection_info.last_activity,
                    'metrics': {
                        'connect_attempts': connection_info.metrics.connect_attempts,
                        'successful_connections': connection_info.metrics.successful_connections,
                        'connection_failures': connection_info.metrics.connection_failures,
                        'uptime': connection_info.metrics.uptime
                    },
                    'is_connected': legacy_manager.is_connected() if legacy_manager else False
                }
            
            return {
                'status': 'healthy',
                'process_id': self.process_id,
                'connections_count': len(self.connections),
                'connections': health_info,
                'stats': self.stats.copy()
            }
            
        except Exception as e:
            self.logger.error(f"Error handling health check: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def _notify_connection_created(self, connection_info: ProcessConnectionInfo):
        """Уведомление о создании connection"""
        if self.ipc_manager:
            await self.ipc_manager.broadcast_message({
                'command': 'connection_created',
                'data': {
                    'process_id': self.process_id,
                    'connection_id': connection_info.connection_id,
                    'role': connection_info.role.value,
                    'created_at': connection_info.created_at
                }
            })
            self.stats['ipc_messages_sent'] += 1
    
    async def _notify_connection_state_changed(self, connection_info: ProcessConnectionInfo):
        """Уведомление об изменении состояния connection"""
        if self.ipc_manager:
            await self.ipc_manager.broadcast_message({
                'command': 'connection_state_changed',
                'data': {
                    'process_id': self.process_id,
                    'connection_id': connection_info.connection_id,
                    'old_state': connection_info.state.value,
                    'new_state': connection_info.state.value,
                    'timestamp': time.time()
                }
            })
            self.stats['ipc_messages_sent'] += 1
    
    async def _load_shared_state(self):
        """Загрузка shared state из файла"""
        try:
            if self.shared_state_file.exists():
                with open(self.shared_state_file, 'r') as f:
                    shared_state = json.load(f)
                
                # Восстановление state если нужно
                self.logger.info("Loaded shared connection state")
            
        except Exception as e:
            self.logger.warning(f"Error loading shared state: {e}")
    
    async def _save_shared_state(self):
        """Сохранение shared state в файл"""
        try:
            shared_state = {
                'process_id': self.process_id,
                'connections': {
                    cid: {
                        'state': info.state.value,
                        'role': info.role.value,
                        'last_activity': info.last_activity
                    }
                    for cid, info in self.connections.items()
                },
                'timestamp': time.time()
            }
            
            with self.state_lock:
                with open(self.shared_state_file, 'w') as f:
                    json.dump(shared_state, f, indent=2)
            
            self.logger.debug("Saved shared connection state")
            
        except Exception as e:
            self.logger.error(f"Error saving shared state: {e}")
    
    async def _monitoring_loop(self):
        """Цикл мониторинга connections"""
        while self.monitoring_enabled:
            try:
                # Health check всех connections
                for connection_id in list(self.connections.keys()):
                    await self._health_check_connection(connection_id)
                
                # Сохранение shared state
                await self._save_shared_state()
                
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _health_check_connection(self, connection_id: str):
        """Health check конкретного connection"""
        try:
            if connection_id not in self.connections:
                return
            
            connection_info = self.connections[connection_id]
            legacy_manager = self.legacy_managers[connection_id]
            
            # Проверка активности
            if not connection_info.is_active():
                self.logger.warning(f"Connection {connection_id} inactive, attempting recovery")
                
                if self.recovery_enabled:
                    await self._attempt_connection_recovery(connection_id)
            
            # Health check через legacy manager
            if legacy_manager and connection_info.state == ConnectionState.CONNECTED:
                is_healthy = await legacy_manager.health_check()
                
                if not is_healthy:
                    self.logger.warning(f"Connection {connection_id} health check failed")
                    connection_info.state = ConnectionState.FAILED
                    
                    if self.recovery_enabled:
                        await self._attempt_connection_recovery(connection_id)
                        
        except Exception as e:
            self.logger.error(f"Error in health check for connection {connection_id}: {e}")
    
    async def _attempt_connection_recovery(self, connection_id: str):
        """Попытка восстановления connection"""
        try:
            if connection_id not in self.connections:
                return
            
            connection_info = self.connections[connection_id]
            connection_info.state = ConnectionState.RECONNECTING
            
            self.stats['recovery_attempts'] += 1
            
            # Попытка переподключения
            success = await self.connect(connection_id)
            
            if success:
                self.stats['successful_recoveries'] += 1
                self.logger.info(f"Successfully recovered connection {connection_id}")
            else:
                self.logger.error(f"Failed to recover connection {connection_id}")
                
        except Exception as e:
            self.logger.error(f"Error attempting recovery for connection {connection_id}: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики Connection Manager"""
        return {
            'process_id': self.process_id,
            'connections_count': len(self.connections),
            'pools_count': len(self.connection_pools),
            'connection_states': {
                state.value: sum(1 for c in self.connections.values() if c.state == state)
                for state in ConnectionState
            },
            'connection_roles': {
                role.value: sum(1 for c in self.connections.values() if c.role == role)
                for role in ConnectionRole
            },
            'statistics': self.stats.copy()
        }
