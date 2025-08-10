"""
Enhanced IPC Commands - Complete CLI Integration

Расширенная система IPC команд для полной интеграции CLI operations
с ProcessSupervisor multi-bot архитектурой.

Функции:
- Complete CLI command mapping
- Multi-process command routing
- Administrative operations
- Bot lifecycle commands
- Real-time monitoring commands
- Configuration management commands
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from src.processsupervisor.communication.ipc_communication import IPCManager, IPCMessage, MessageType, MessagePriority

# Phase 2C Integration: Database coordination imports
from src.database.integration import DatabaseIntegrationManager


class CommandCategory(Enum):
    """Категории IPC команд"""
    ADMIN = "admin"
    BOT_LIFECYCLE = "bot_lifecycle"
    MONITORING = "monitoring"
    CONFIGURATION = "configuration"
    CONNECTION = "connection"
    SYSTEM = "system"


class CommandScope(Enum):
    """Области действия команд"""
    GLOBAL = "global"        # Команды для всей системы
    PROCESS = "process"      # Команды для конкретного процесса
    BOT = "bot"             # Команды для конкретного бота
    CONNECTION = "connection" # Команды для connection


@dataclass
class CommandDefinition:
    """Определение IPC команды"""
    name: str
    category: CommandCategory
    scope: CommandScope
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_permissions: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None
    timeout: float = 30.0
    priority: MessagePriority = MessagePriority.NORMAL


@dataclass
class CommandResult:
    """Результат выполнения команды"""
    command_name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time: float = 0.0
    timestamp: float = field(default_factory=time.time)


class EnhancedIPCCommands:
    """
    Enhanced IPC Commands - полная система CLI команд для ProcessSupervisor
    
    Функции:
    - Complete command registry с категоризацией
    - Multi-process command routing и execution
    - Administrative operations (старт/стоп/рестарт)
    - Bot lifecycle management
    - Real-time monitoring и metrics
    - Configuration management
    """
    
    def __init__(self, process_id: str, ipc_manager: IPCManager):
        self.process_id = process_id
        self.ipc_manager = ipc_manager
        self.logger = logging.getLogger(__name__)
        
        # Phase 2C Integration: Database coordination
        self.db_integration = DatabaseIntegrationManager(bot_id=process_id)
        self._db_initialized = False
        
        # Command registry
        self.commands: Dict[str, CommandDefinition] = {}
        self.command_handlers: Dict[str, Callable] = {}
        
        # Execution tracking
        self.command_history: List[CommandResult] = []
        self.active_commands: Dict[str, float] = {}
        
        # Permission system
        self.permissions: Dict[str, List[str]] = {
            'admin': ['*'],  # Admin имеет все права
            'monitor': ['monitoring.*', 'system.status'],
            'operator': ['bot_lifecycle.*', 'monitoring.*']
        }
        
        # Statistics
        self.stats = {
            'commands_executed': 0,
            'commands_failed': 0,
            'avg_execution_time': 0.0,
            'total_execution_time': 0.0
        }
        
        # Initialization
        self._initialize_core_commands()
    
    async def start(self):
        """Запуск Enhanced IPC Commands"""
        try:
            self.logger.info(f"Starting Enhanced IPC Commands for process {self.process_id}")
            
            # Регистрация handlers в IPC Manager
            await self._register_command_handlers()
            
            # Загрузка дополнительных команд
            await self._load_external_commands()
            
            self.logger.info(f"Enhanced IPC Commands started with {len(self.commands)} commands")
            
        except Exception as e:
            self.logger.error(f"Error starting Enhanced IPC Commands: {e}")
            raise
    
    async def stop(self):
        """Остановка Enhanced IPC Commands"""
        try:
            self.logger.info("Stopping Enhanced IPC Commands")
            
            # Завершение активных команд
            for command_id in list(self.active_commands.keys()):
                self.logger.warning(f"Cancelling active command {command_id}")
                del self.active_commands[command_id]
            
            self.logger.info("Enhanced IPC Commands stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Enhanced IPC Commands: {e}")
    
    def _initialize_core_commands(self):
        """Инициализация основных команд"""
        
        # =============================================================================
        # ADMINISTRATIVE COMMANDS
        # =============================================================================
        
        self.register_command(CommandDefinition(
            name="admin.start_bot",
            category=CommandCategory.ADMIN,
            scope=CommandScope.BOT,
            description="Запуск бота",
            parameters={
                'bot_id': {'type': str, 'required': True},
                'config_override': {'type': dict, 'required': False}
            },
            required_permissions=['admin', 'bot_lifecycle.start'],
            handler=self._handle_start_bot
        ))
        
        self.register_command(CommandDefinition(
            name="admin.stop_bot",
            category=CommandCategory.ADMIN,
            scope=CommandScope.BOT,
            description="Остановка бота",
            parameters={
                'bot_id': {'type': str, 'required': True},
                'graceful': {'type': bool, 'required': False, 'default': True}
            },
            required_permissions=['admin', 'bot_lifecycle.stop'],
            handler=self._handle_stop_bot
        ))
        
        self.register_command(CommandDefinition(
            name="admin.restart_bot",
            category=CommandCategory.ADMIN,
            scope=CommandScope.BOT,
            description="Перезапуск бота",
            parameters={
                'bot_id': {'type': str, 'required': True},
                'config_override': {'type': dict, 'required': False}
            },
            required_permissions=['admin', 'bot_lifecycle.restart'],
            handler=self._handle_restart_bot
        ))
        
        self.register_command(CommandDefinition(
            name="admin.shutdown_system",
            category=CommandCategory.ADMIN,
            scope=CommandScope.GLOBAL,
            description="Полная остановка системы",
            parameters={
                'graceful': {'type': bool, 'required': False, 'default': True},
                'timeout': {'type': float, 'required': False, 'default': 60.0}
            },
            required_permissions=['admin'],
            handler=self._handle_shutdown_system
        ))
        
        # =============================================================================
        # BOT LIFECYCLE COMMANDS
        # =============================================================================
        
        self.register_command(CommandDefinition(
            name="bot.list",
            category=CommandCategory.BOT_LIFECYCLE,
            scope=CommandScope.GLOBAL,
            description="Список всех ботов",
            parameters={
                'include_inactive': {'type': bool, 'required': False, 'default': False}
            },
            required_permissions=['monitor', 'bot_lifecycle.list'],
            handler=self._handle_list_bots
        ))
        
        self.register_command(CommandDefinition(
            name="bot.status",
            category=CommandCategory.BOT_LIFECYCLE,
            scope=CommandScope.BOT,
            description="Статус конкретного бота",
            parameters={
                'bot_id': {'type': str, 'required': True}
            },
            required_permissions=['monitor', 'bot_lifecycle.status'],
            handler=self._handle_bot_status
        ))
        
        self.register_command(CommandDefinition(
            name="bot.logs",
            category=CommandCategory.BOT_LIFECYCLE,
            scope=CommandScope.BOT,
            description="Логи бота",
            parameters={
                'bot_id': {'type': str, 'required': True},
                'lines': {'type': int, 'required': False, 'default': 100},
                'level': {'type': str, 'required': False, 'default': 'INFO'}
            },
            required_permissions=['monitor', 'bot_lifecycle.logs'],
            handler=self._handle_bot_logs
        ))
        
        # =============================================================================
        # DATABASE INTEGRATION COMMANDS (Phase 2C)
        # =============================================================================
        
        self.register_command(CommandDefinition(
            name="database.status",
            category=CommandCategory.SYSTEM,
            scope=CommandScope.GLOBAL,
            description="Статус интеграции с базой данных",
            parameters={
                'bot_id': {'type': str, 'required': False}
            },
            required_permissions=['monitor', 'admin'],
            handler=self._handle_database_status
        ))
        
        self.register_command(CommandDefinition(
            name="database.enable_migration",
            category=CommandCategory.ADMIN,
            scope=CommandScope.BOT,
            description="Включить миграцию данных для бота",
            parameters={
                'bot_id': {'type': str, 'required': True}
            },
            required_permissions=['admin'],
            handler=self._handle_enable_migration
        ))
        
        self.register_command(CommandDefinition(
            name="database.disable_migration",
            category=CommandCategory.ADMIN,
            scope=CommandScope.BOT,
            description="Отключить миграцию данных для бота",
            parameters={
                'bot_id': {'type': str, 'required': True}
            },
            required_permissions=['admin'],
            handler=self._handle_disable_migration
        ))
        
        self.register_command(CommandDefinition(
            name="database.cache_stats",
            category=CommandCategory.MONITORING,
            scope=CommandScope.GLOBAL,
            description="Статистика кэширования",
            parameters={},
            required_permissions=['monitor'],
            handler=self._handle_cache_stats
        ))
        
        # =============================================================================
        # MONITORING COMMANDS
        # =============================================================================
        
        self.register_command(CommandDefinition(
            name="monitor.system_status",
            category=CommandCategory.MONITORING,
            scope=CommandScope.GLOBAL,
            description="Общий статус системы",
            parameters={},
            required_permissions=['monitor'],
            handler=self._handle_system_status
        ))
        
        self.register_command(CommandDefinition(
            name="monitor.process_status",
            category=CommandCategory.MONITORING,
            scope=CommandScope.PROCESS,
            description="Статус процесса",
            parameters={
                'process_id': {'type': str, 'required': False}  # Если не указан, текущий
            },
            required_permissions=['monitor'],
            handler=self._handle_process_status
        ))
        
        self.register_command(CommandDefinition(
            name="monitor.metrics",
            category=CommandCategory.MONITORING,
            scope=CommandScope.GLOBAL,
            description="Метрики системы",
            parameters={
                'time_range': {'type': str, 'required': False, 'default': '1h'},
                'metric_types': {'type': list, 'required': False}
            },
            required_permissions=['monitor'],
            handler=self._handle_metrics
        ))
        
        self.register_command(CommandDefinition(
            name="monitor.health_check",
            category=CommandCategory.MONITORING,
            scope=CommandScope.GLOBAL,
            description="Health check всей системы",
            parameters={
                'deep_check': {'type': bool, 'required': False, 'default': False}
            },
            required_permissions=['monitor'],
            handler=self._handle_health_check
        ))
        
        # =============================================================================
        # CONFIGURATION COMMANDS
        # =============================================================================
        
        self.register_command(CommandDefinition(
            name="config.get",
            category=CommandCategory.CONFIGURATION,
            scope=CommandScope.BOT,
            description="Получение конфигурации",
            parameters={
                'bot_id': {'type': str, 'required': False},
                'config_path': {'type': str, 'required': False}
            },
            required_permissions=['monitor', 'config.read'],
            handler=self._handle_config_get
        ))
        
        self.register_command(CommandDefinition(
            name="config.set",
            category=CommandCategory.CONFIGURATION,
            scope=CommandScope.BOT,
            description="Установка конфигурации",
            parameters={
                'bot_id': {'type': str, 'required': False},
                'config_path': {'type': str, 'required': True},
                'value': {'type': 'any', 'required': True}
            },
            required_permissions=['admin', 'config.write'],
            handler=self._handle_config_set
        ))
        
        self.register_command(CommandDefinition(
            name="config.reload",
            category=CommandCategory.CONFIGURATION,
            scope=CommandScope.BOT,
            description="Перезагрузка конфигурации",
            parameters={
                'bot_id': {'type': str, 'required': False}
            },
            required_permissions=['admin', 'config.reload'],
            handler=self._handle_config_reload
        ))
        
        # =============================================================================
        # CONNECTION COMMANDS
        # =============================================================================
        
        self.register_command(CommandDefinition(
            name="connection.list",
            category=CommandCategory.CONNECTION,
            scope=CommandScope.GLOBAL,
            description="Список connections",
            parameters={
                'process_id': {'type': str, 'required': False}
            },
            required_permissions=['monitor', 'connection.list'],
            handler=self._handle_connection_list
        ))
        
        self.register_command(CommandDefinition(
            name="connection.status",
            category=CommandCategory.CONNECTION,
            scope=CommandScope.CONNECTION,
            description="Статус connection",
            parameters={
                'connection_id': {'type': str, 'required': True}
            },
            required_permissions=['monitor', 'connection.status'],
            handler=self._handle_connection_status
        ))
        
        self.register_command(CommandDefinition(
            name="connection.restart",
            category=CommandCategory.CONNECTION,
            scope=CommandScope.CONNECTION,
            description="Перезапуск connection",
            parameters={
                'connection_id': {'type': str, 'required': True}
            },
            required_permissions=['admin', 'connection.restart'],
            handler=self._handle_connection_restart
        ))
        
        # =============================================================================
        # SYSTEM COMMANDS
        # =============================================================================
        
        self.register_command(CommandDefinition(
            name="system.info",
            category=CommandCategory.SYSTEM,
            scope=CommandScope.GLOBAL,
            description="Информация о системе",
            parameters={},
            required_permissions=['monitor'],
            handler=self._handle_system_info
        ))
        
        self.register_command(CommandDefinition(
            name="system.commands",
            category=CommandCategory.SYSTEM,
            scope=CommandScope.GLOBAL,
            description="Список доступных команд",
            parameters={
                'category': {'type': str, 'required': False},
                'scope': {'type': str, 'required': False}
            },
            required_permissions=['monitor'],
            handler=self._handle_system_commands
        ))
    
    def register_command(self, command_def: CommandDefinition):
        """Регистрация новой команды"""
        self.commands[command_def.name] = command_def
        
        if command_def.handler:
            self.command_handlers[command_def.name] = command_def.handler
        
        self.logger.debug(f"Registered command: {command_def.name}")
    
    async def execute_command(self, command_name: str, parameters: Dict[str, Any] = None,
                            user_permissions: List[str] = None) -> CommandResult:
        """Выполнение команды"""
        start_time = time.time()
        command_id = f"{command_name}_{int(start_time)}"
        
        try:
            # Проверка существования команды
            if command_name not in self.commands:
                return CommandResult(
                    command_name=command_name,
                    success=False,
                    error=f"Command '{command_name}' not found"
                )
            
            command_def = self.commands[command_name]
            parameters = parameters or {}
            
            # Проверка permissions
            if not self._check_permissions(command_def, user_permissions or []):
                return CommandResult(
                    command_name=command_name,
                    success=False,
                    error="Insufficient permissions"
                )
            
            # Валидация параметров
            validation_error = self._validate_parameters(command_def, parameters)
            if validation_error:
                return CommandResult(
                    command_name=command_name,
                    success=False,
                    error=validation_error
                )
            
            # Выполнение команды
            self.active_commands[command_id] = start_time
            
            if command_name in self.command_handlers:
                handler = self.command_handlers[command_name]
                result_data = await handler(parameters)
                
                execution_time = time.time() - start_time
                
                result = CommandResult(
                    command_name=command_name,
                    success=True,
                    data=result_data,
                    execution_time=execution_time
                )
                
                # Обновление статистики
                self._update_stats(execution_time, success=True)
                
            else:
                # Роутинг команды через IPC
                result = await self._route_command_via_ipc(command_def, parameters)
            
            # Cleanup
            if command_id in self.active_commands:
                del self.active_commands[command_id]
            
            # Сохранение в историю
            self.command_history.append(result)
            if len(self.command_history) > 1000:  # Ограничение размера истории
                self.command_history = self.command_history[-500:]
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Error executing command {command_name}: {e}")
            
            self._update_stats(execution_time, success=False)
            
            if command_id in self.active_commands:
                del self.active_commands[command_id]
            
            return CommandResult(
                command_name=command_name,
                success=False,
                error=str(e),
                execution_time=execution_time
            )
    
    async def _register_command_handlers(self):
        """Регистрация command handlers в IPC Manager"""
        
        # Основной handler для команд
        self.ipc_manager.register_handler(
            self.process_id,
            "execute_command",
            self._handle_ipc_command
        )
        
        # Handler для получения списка команд
        self.ipc_manager.register_handler(
            self.process_id,
            "get_commands",
            self._handle_get_commands
        )
        
        # Handler для command routing
        self.ipc_manager.register_handler(
            self.process_id,
            "route_command",
            self._handle_route_command
        )
    
    async def _handle_ipc_command(self, message: IPCMessage) -> Dict[str, Any]:
        """Handler для выполнения команд через IPC"""
        try:
            command_name = message.data.get('command_name')
            parameters = message.data.get('parameters', {})
            user_permissions = message.data.get('user_permissions', [])
            
            result = await self.execute_command(command_name, parameters, user_permissions)
            
            return {
                'success': result.success,
                'data': result.data,
                'error': result.error,
                'execution_time': result.execution_time
            }
            
        except Exception as e:
            self.logger.error(f"Error handling IPC command: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_commands(self, message: IPCMessage) -> Dict[str, Any]:
        """Handler для получения списка команд"""
        try:
            category = message.data.get('category')
            scope = message.data.get('scope')
            
            filtered_commands = {}
            
            for name, cmd_def in self.commands.items():
                if category and cmd_def.category.value != category:
                    continue
                if scope and cmd_def.scope.value != scope:
                    continue
                
                filtered_commands[name] = {
                    'category': cmd_def.category.value,
                    'scope': cmd_def.scope.value,
                    'description': cmd_def.description,
                    'parameters': cmd_def.parameters,
                    'permissions': cmd_def.required_permissions
                }
            
            return {
                'success': True,
                'commands': filtered_commands
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_route_command(self, message: IPCMessage) -> Dict[str, Any]:
        """Handler для роутинга команд между процессами"""
        try:
            # Реализация роутинга команд
            target_process = message.data.get('target_process')
            command_name = message.data.get('command_name')
            parameters = message.data.get('parameters', {})
            
            # Перенаправление команды в целевой процесс
            if target_process and target_process != self.process_id:
                routed_message = IPCMessage(
                    message_id=f"routed_{message.message_id}",
                    sender_id=self.process_id,
                    recipient_id=target_process,
                    message_type=MessageType.COMMAND,
                    data={
                        'command_name': command_name,
                        'parameters': parameters,
                        'original_sender': message.sender_id
                    }
                )
                
                response = await self.ipc_manager.send_message(routed_message)
                return response
            
            # Выполнение локально
            result = await self.execute_command(command_name, parameters)
            
            return {
                'success': result.success,
                'data': result.data,
                'error': result.error
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    # =============================================================================
    # COMMAND HANDLERS IMPLEMENTATION
    # =============================================================================
    
    async def _handle_start_bot(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для запуска бота"""
        bot_id = parameters['bot_id']
        config_override = parameters.get('config_override', {})
        
        # Отправка команды в ProcessSupervisor
        message = IPCMessage(
            message_id=f"start_bot_{bot_id}_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.COMMAND,
            data={
                'action': 'start_bot',
                'bot_id': bot_id,
                'config_override': config_override
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_stop_bot(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для остановки бота"""
        bot_id = parameters['bot_id']
        graceful = parameters.get('graceful', True)
        
        message = IPCMessage(
            message_id=f"stop_bot_{bot_id}_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.COMMAND,
            data={
                'action': 'stop_bot',
                'bot_id': bot_id,
                'graceful': graceful
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_restart_bot(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для перезапуска бота"""
        bot_id = parameters['bot_id']
        config_override = parameters.get('config_override', {})
        
        message = IPCMessage(
            message_id=f"restart_bot_{bot_id}_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.COMMAND,
            data={
                'action': 'restart_bot',
                'bot_id': bot_id,
                'config_override': config_override
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_shutdown_system(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для остановки системы"""
        graceful = parameters.get('graceful', True)
        timeout = parameters.get('timeout', 60.0)
        
        message = IPCMessage(
            message_id=f"shutdown_system_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.COMMAND,
            priority=MessagePriority.HIGH,
            data={
                'action': 'shutdown_system',
                'graceful': graceful,
                'timeout': timeout
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_list_bots(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для получения списка ботов"""
        include_inactive = parameters.get('include_inactive', False)
        
        message = IPCMessage(
            message_id=f"list_bots_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.QUERY,
            data={
                'action': 'list_bots',
                'include_inactive': include_inactive
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_bot_status(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для получения статуса бота"""
        bot_id = parameters['bot_id']
        
        message = IPCMessage(
            message_id=f"bot_status_{bot_id}_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.QUERY,
            data={
                'action': 'get_bot_status',
                'bot_id': bot_id
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_bot_logs(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для получения логов бота"""
        bot_id = parameters['bot_id']
        lines = parameters.get('lines', 100)
        level = parameters.get('level', 'INFO')
        
        # Чтение логов из файла
        log_file = Path(f"logs/{bot_id}.log")
        
        if not log_file.exists():
            return {
                'bot_id': bot_id,
                'logs': [],
                'message': 'Log file not found'
            }
        
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                
            # Фильтрация по уровню
            filtered_lines = []
            for line in all_lines[-lines:]:
                if level.upper() in line.upper():
                    filtered_lines.append(line.strip())
            
            return {
                'bot_id': bot_id,
                'logs': filtered_lines,
                'total_lines': len(filtered_lines)
            }
            
        except Exception as e:
            return {
                'bot_id': bot_id,
                'error': str(e)
            }
    
    async def _handle_system_status(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для получения статуса системы"""
        message = IPCMessage(
            message_id=f"system_status_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.QUERY,
            data={'action': 'get_system_status'}
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_process_status(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для получения статуса процесса"""
        target_process = parameters.get('process_id', self.process_id)
        
        message = IPCMessage(
            message_id=f"process_status_{target_process}_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id=target_process,
            message_type=MessageType.QUERY,
            data={'action': 'get_process_status'}
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_metrics(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для получения метрик"""
        time_range = parameters.get('time_range', '1h')
        metric_types = parameters.get('metric_types')
        
        message = IPCMessage(
            message_id=f"metrics_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.QUERY,
            data={
                'action': 'get_metrics',
                'time_range': time_range,
                'metric_types': metric_types
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_health_check(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для health check"""
        deep_check = parameters.get('deep_check', False)
        
        message = IPCMessage(
            message_id=f"health_check_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id="process_supervisor",
            message_type=MessageType.QUERY,
            data={
                'action': 'health_check',
                'deep_check': deep_check
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_config_get(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для получения конфигурации"""
        bot_id = parameters.get('bot_id')
        config_path = parameters.get('config_path')
        
        target_process = bot_id if bot_id else "process_supervisor"
        
        message = IPCMessage(
            message_id=f"config_get_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id=target_process,
            message_type=MessageType.QUERY,
            data={
                'action': 'get_config',
                'bot_id': bot_id,
                'config_path': config_path
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_config_set(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для установки конфигурации"""
        bot_id = parameters.get('bot_id')
        config_path = parameters['config_path']
        value = parameters['value']
        
        target_process = bot_id if bot_id else "process_supervisor"
        
        message = IPCMessage(
            message_id=f"config_set_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id=target_process,
            message_type=MessageType.COMMAND,
            data={
                'action': 'set_config',
                'bot_id': bot_id,
                'config_path': config_path,
                'value': value
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_config_reload(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для перезагрузки конфигурации"""
        bot_id = parameters.get('bot_id')
        
        target_process = bot_id if bot_id else "process_supervisor"
        
        message = IPCMessage(
            message_id=f"config_reload_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id=target_process,
            message_type=MessageType.COMMAND,
            data={
                'action': 'reload_config',
                'bot_id': bot_id
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_connection_list(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для списка connections"""
        target_process = parameters.get('process_id', "all")
        
        if target_process == "all":
            # Broadcast запрос ко всем процессам
            message = IPCMessage(
                message_id=f"connection_list_{int(time.time())}",
                sender_id=self.process_id,
                recipient_id="broadcast",
                message_type=MessageType.QUERY,
                data={'action': 'list_connections'}
            )
        else:
            message = IPCMessage(
                message_id=f"connection_list_{target_process}_{int(time.time())}",
                sender_id=self.process_id,
                recipient_id=target_process,
                message_type=MessageType.QUERY,
                data={'action': 'list_connections'}
            )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_connection_status(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для статуса connection"""
        connection_id = parameters['connection_id']
        
        # Извлечение process_id из connection_id
        process_id = connection_id.split('_')[0] if '_' in connection_id else "process_supervisor"
        
        message = IPCMessage(
            message_id=f"connection_status_{connection_id}_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id=process_id,
            message_type=MessageType.QUERY,
            data={
                'action': 'get_connection_status',
                'connection_id': connection_id
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_connection_restart(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для перезапуска connection"""
        connection_id = parameters['connection_id']
        
        # Извлечение process_id из connection_id
        process_id = connection_id.split('_')[0] if '_' in connection_id else "process_supervisor"
        
        message = IPCMessage(
            message_id=f"connection_restart_{connection_id}_{int(time.time())}",
            sender_id=self.process_id,
            recipient_id=process_id,
            message_type=MessageType.COMMAND,
            data={
                'action': 'restart_connection',
                'connection_id': connection_id
            }
        )
        
        response = await self.ipc_manager.send_message(message)
        return response
    
    async def _handle_system_info(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для информации о системе"""
        import platform
        import psutil
        
        return {
            'system_info': {
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'cpu_count': psutil.cpu_count(),
                'memory_total': psutil.virtual_memory().total,
                'memory_available': psutil.virtual_memory().available,
                'disk_usage': psutil.disk_usage('/').percent
            },
            'process_info': {
                'process_id': self.process_id,
                'commands_registered': len(self.commands),
                'commands_executed': self.stats['commands_executed'],
                'avg_execution_time': self.stats['avg_execution_time']
            }
        }
    
    async def _handle_system_commands(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для списка команд"""
        category = parameters.get('category')
        scope = parameters.get('scope')
        
        filtered_commands = {}
        
        for name, cmd_def in self.commands.items():
            if category and cmd_def.category.value != category:
                continue
            if scope and cmd_def.scope.value != scope:
                continue
            
            filtered_commands[name] = {
                'category': cmd_def.category.value,
                'scope': cmd_def.scope.value,
                'description': cmd_def.description,
                'parameters': cmd_def.parameters,
                'permissions': cmd_def.required_permissions
            }
        
        return {
            'commands': filtered_commands,
            'total_count': len(filtered_commands),
            'categories': list(set(cmd.category.value for cmd in self.commands.values())),
            'scopes': list(set(cmd.scope.value for cmd in self.commands.values()))
        }
    
    # =============================================================================
    # DATABASE INTEGRATION HANDLERS (Phase 2C)
    # =============================================================================
    
    async def _handle_database_status(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для статуса интеграции с базой данных"""
        try:
            bot_id = parameters.get('bot_id', self.process_id)
            
            if not self._db_initialized:
                # Try to initialize if not already done
                success = await self.db_integration.initialize()
                if success:
                    self._db_initialized = True
            
            if self._db_initialized:
                status = await self.db_integration.get_status()
                migration_status = await self.db_integration.get_migration_status()
                cache_stats = await self.db_integration.get_cache_stats()
                
                return {
                    'status': 'initialized',
                    'bot_id': bot_id,
                    'database_status': status,
                    'migration_status': migration_status,
                    'cache_stats': cache_stats
                }
            else:
                return {
                    'status': 'not_initialized',
                    'bot_id': bot_id,
                    'error': 'Database integration not initialized'
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def _handle_enable_migration(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для включения миграции данных"""
        try:
            bot_id = parameters['bot_id']
            
            if not self._db_initialized:
                success = await self.db_integration.initialize(enable_migration=True)
                if success:
                    self._db_initialized = True
                else:
                    return {'status': 'error', 'error': 'Failed to initialize database integration'}
            
            success = await self.db_integration.enable_migration()
            
            return {
                'status': 'success' if success else 'error',
                'bot_id': bot_id,
                'migration_enabled': success
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def _handle_disable_migration(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для отключения миграции данных"""
        try:
            bot_id = parameters['bot_id']
            
            if self._db_initialized:
                success = await self.db_integration.disable_migration()
                return {
                    'status': 'success' if success else 'error',
                    'bot_id': bot_id,
                    'migration_enabled': not success
                }
            else:
                return {
                    'status': 'error',
                    'error': 'Database integration not initialized'
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def _handle_cache_stats(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handler для статистики кэширования"""
        try:
            if self._db_initialized:
                cache_stats = await self.db_integration.get_cache_stats()
                performance_metrics = await self.db_integration.get_performance_metrics()
                
                return {
                    'status': 'success',
                    'cache_stats': cache_stats,
                    'performance_metrics': performance_metrics
                }
            else:
                return {
                    'status': 'error',
                    'error': 'Database integration not initialized'
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    # =============================================================================
    # UTILITY METHODS
    # =============================================================================
    
    def _check_permissions(self, command_def: CommandDefinition, user_permissions: List[str]) -> bool:
        """Проверка permissions для команды"""
        if not command_def.required_permissions:
            return True
        
        # Admin имеет все права
        if 'admin' in user_permissions:
            return True
        
        # Проверка конкретных permissions
        for required_perm in command_def.required_permissions:
            if required_perm in user_permissions:
                return True
            
            # Проверка wildcard permissions
            for user_perm in user_permissions:
                if user_perm.endswith('*'):
                    prefix = user_perm[:-1]
                    if required_perm.startswith(prefix):
                        return True
        
        return False
    
    def _validate_parameters(self, command_def: CommandDefinition, parameters: Dict[str, Any]) -> Optional[str]:
        """Валидация параметров команды"""
        for param_name, param_info in command_def.parameters.items():
            required = param_info.get('required', False)
            param_type = param_info.get('type')
            
            if required and param_name not in parameters:
                return f"Required parameter '{param_name}' is missing"
            
            if param_name in parameters:
                value = parameters[param_name]
                
                # Проверка типа
                if param_type and param_type != 'any':
                    if param_type == str and not isinstance(value, str):
                        return f"Parameter '{param_name}' must be string"
                    elif param_type == int and not isinstance(value, int):
                        return f"Parameter '{param_name}' must be integer"
                    elif param_type == bool and not isinstance(value, bool):
                        return f"Parameter '{param_name}' must be boolean"
                    elif param_type == dict and not isinstance(value, dict):
                        return f"Parameter '{param_name}' must be object"
                    elif param_type == list and not isinstance(value, list):
                        return f"Parameter '{param_name}' must be array"
        
        return None
    
    async def _route_command_via_ipc(self, command_def: CommandDefinition, parameters: Dict[str, Any]) -> CommandResult:
        """Роутинг команды через IPC"""
        try:
            # Определение целевого процесса на основе scope
            if command_def.scope == CommandScope.GLOBAL:
                target_process = "process_supervisor"
            elif command_def.scope == CommandScope.BOT:
                bot_id = parameters.get('bot_id')
                target_process = bot_id if bot_id else "process_supervisor"
            elif command_def.scope == CommandScope.CONNECTION:
                connection_id = parameters.get('connection_id', '')
                target_process = connection_id.split('_')[0] if '_' in connection_id else self.process_id
            else:
                target_process = self.process_id
            
            message = IPCMessage(
                message_id=f"route_{command_def.name}_{int(time.time())}",
                sender_id=self.process_id,
                recipient_id=target_process,
                message_type=MessageType.COMMAND,
                data={
                    'command_name': command_def.name,
                    'parameters': parameters
                }
            )
            
            start_time = time.time()
            response = await self.ipc_manager.send_message(message)
            execution_time = time.time() - start_time
            
            return CommandResult(
                command_name=command_def.name,
                success=response.get('success', False),
                data=response.get('data', {}),
                error=response.get('error'),
                execution_time=execution_time
            )
            
        except Exception as e:
            return CommandResult(
                command_name=command_def.name,
                success=False,
                error=str(e)
            )
    
    def _update_stats(self, execution_time: float, success: bool):
        """Обновление статистики выполнения команд"""
        if success:
            self.stats['commands_executed'] += 1
        else:
            self.stats['commands_failed'] += 1
        
        self.stats['total_execution_time'] += execution_time
        
        total_commands = self.stats['commands_executed'] + self.stats['commands_failed']
        if total_commands > 0:
            self.stats['avg_execution_time'] = self.stats['total_execution_time'] / total_commands
    
    async def _load_external_commands(self):
        """Загрузка внешних команд из конфигурации"""
        try:
            external_commands_file = Path("external_commands.json")
            
            if external_commands_file.exists():
                with open(external_commands_file, 'r') as f:
                    external_commands = json.load(f)
                
                for cmd_data in external_commands.get('commands', []):
                    command_def = CommandDefinition(
                        name=cmd_data['name'],
                        category=CommandCategory(cmd_data['category']),
                        scope=CommandScope(cmd_data['scope']),
                        description=cmd_data['description'],
                        parameters=cmd_data.get('parameters', {}),
                        required_permissions=cmd_data.get('required_permissions', [])
                    )
                    
                    self.register_command(command_def)
                
                self.logger.info(f"Loaded {len(external_commands.get('commands', []))} external commands")
            
        except Exception as e:
            self.logger.warning(f"Error loading external commands: {e}")
    
    def get_command_statistics(self) -> Dict[str, Any]:
        """Получение статистики команд"""
        return {
            'total_commands': len(self.commands),
            'commands_by_category': {
                category.value: sum(1 for cmd in self.commands.values() if cmd.category == category)
                for category in CommandCategory
            },
            'commands_by_scope': {
                scope.value: sum(1 for cmd in self.commands.values() if cmd.scope == scope)
                for scope in CommandScope
            },
            'execution_stats': self.stats.copy(),
            'active_commands': len(self.active_commands),
            'command_history_size': len(self.command_history)
        }
