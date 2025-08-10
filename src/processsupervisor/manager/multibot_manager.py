"""
Multi-Bot Manager - ProcessSupervisor Implementation

Центральный orchestrator для управления жизненным циклом множественных Telegram ботов
в рамках единой системы с process-based isolation.

Основные функции:
- Управление жизненным циклом ботов (create, start, stop, restart, destroy)
- Health monitoring с автоматическим recovery
- Process-level isolation между ботами
- Конфигурация и resource allocation
- IPC communication coordination
- Phase 2B: Enhanced lifecycle management, dynamic configuration, resource optimization

Архитектура: ProcessSupervisor с process-based isolation
"""

import asyncio
import logging
import signal
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set
import psutil
import json

from src.config.config import Config
from src.utils.logger import setup_logger
from src.processsupervisor.process.process_monitor import ProcessMonitor
from src.processsupervisor.communication.ipc_communication import IPCManager
from src.processsupervisor.process.bot_process import BotProcess, BotProcessState

# Phase 2B Enhanced Components
from src.processsupervisor.manager.configuration_manager import ConfigurationManager, ConfigurationScope
from src.processsupervisor.process.resource_allocator import ResourceAllocator, ResourcePriority, AllocationStrategy
from src.processsupervisor.process.process_lifecycle import ProcessLifecycleManager, ProcessState, LifecycleEvent
from src.processsupervisor.optimization.performance_optimizer import PerformanceOptimizer, OptimizationStrategy, MetricType


class ProcessSupervisorState(Enum):
    """Состояния ProcessSupervisor"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class BotConfiguration:
    """Конфигурация отдельного бота"""
    bot_id: str
    bot_token: str
    database_role: str
    max_memory_mb: int = 512
    max_connections: int = 10
    restart_policy: str = "always"  # always, never, on-failure
    startup_timeout: int = 30
    health_check_interval: int = 60
    environment_vars: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Конвертация в словарь для передачи в процесс"""
        return {
            'bot_id': self.bot_id,
            'bot_token': self.bot_token,
            'database_role': self.database_role,
            'max_memory_mb': self.max_memory_mb,
            'max_connections': self.max_connections,
            'restart_policy': self.restart_policy,
            'startup_timeout': self.startup_timeout,
            'health_check_interval': self.health_check_interval,
            'environment_vars': self.environment_vars
        }


class MultiBotManager:
    """
    ProcessSupervisor для управления множественными Telegram ботами
    
    Основные возможности:
    - Process-based isolation между ботами
    - Автоматический health monitoring и recovery
    - Управление ресурсами и конфигурацией
    - IPC communication между процессами
    - Graceful shutdown и startup sequences
    - Phase 2B: Enhanced lifecycle management, dynamic configuration, optimization
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(__name__)
        self.state = ProcessSupervisorState.INITIALIZING
        
        # Core components (Phase 2A)
        self.process_monitor = ProcessMonitor()
        self.ipc_manager = IPCManager()
        
        # Phase 2B Enhanced Components
        self.configuration_manager = ConfigurationManager(
            config_dir=Path("configs"),
            base_config=config
        )
        self.resource_allocator = ResourceAllocator(
            strategy=AllocationStrategy.ADAPTIVE
        )
        self.lifecycle_manager = ProcessLifecycleManager()
        self.performance_optimizer = PerformanceOptimizer(
            strategy=OptimizationStrategy.ADAPTIVE
        )
        
        # Bot management
        self.bot_processes: Dict[str, BotProcess] = {}
        self.bot_configurations: Dict[str, BotConfiguration] = {}
        
        # Resource tracking
        self.resource_limits = {
            'max_total_memory_mb': 2048,  # 2GB total
            'max_concurrent_bots': 10,
            'max_cpu_percent': 80.0
        }
        
        # Shutdown handling
        self._shutdown_event = asyncio.Event()
        self._setup_signal_handlers()
        
        self.logger.info("MultiBotManager initialized in ProcessSupervisor mode")
    
    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов для graceful shutdown"""
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов завершения"""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
        asyncio.create_task(self.shutdown())
    
    async def start(self):
        """Запуск ProcessSupervisor с Phase 2B Enhanced Components"""
        try:
            self.logger.info("Starting MultiBotManager ProcessSupervisor with Phase 2B enhancements")
            self.state = ProcessSupervisorState.RUNNING
            
            # Phase 2A Components
            await self.process_monitor.start()
            await self.ipc_manager.start()
            
            # Phase 2B Enhanced Components
            await self.configuration_manager.start()
            await self.resource_allocator.start()
            await self.lifecycle_manager.start()
            await self.performance_optimizer.start()
            
            # Setup lifecycle hooks
            self._setup_lifecycle_hooks()
            
            # Setup performance callbacks
            self._setup_performance_callbacks()
            
            # Загрузка конфигураций ботов
            await self._load_bot_configurations()
            
            # Автозапуск ботов (если настроен)
            await self._auto_start_bots()
            
            # Основной цикл мониторинга
            await self._main_monitoring_loop()
            
        except Exception as e:
            self.logger.error(f"Error starting ProcessSupervisor: {e}")
            self.state = ProcessSupervisorState.ERROR
            raise
    
    def _setup_lifecycle_hooks(self):
        """Настройка lifecycle hooks для интеграции с Phase 2B компонентами"""
        try:
            # Hooks для начала процесса
            self.lifecycle_manager.register_lifecycle_hook(
                LifecycleEvent.BEFORE_START,
                self._on_before_start,
                priority=1,
                description="Resource allocation and configuration preparation"
            )
            
            self.lifecycle_manager.register_lifecycle_hook(
                LifecycleEvent.AFTER_START,
                self._on_after_start,
                priority=1,
                description="Performance monitoring setup"
            )
            
            # Hooks для остановки процесса
            self.lifecycle_manager.register_lifecycle_hook(
                LifecycleEvent.BEFORE_STOP,
                self._on_before_stop,
                priority=1,
                description="Graceful shutdown preparation"
            )
            
            self.lifecycle_manager.register_lifecycle_hook(
                LifecycleEvent.AFTER_STOP,
                self._on_after_stop,
                priority=1,
                description="Resource cleanup and deallocation"
            )
            
            # Hooks для обработки ошибок
            self.lifecycle_manager.register_lifecycle_hook(
                LifecycleEvent.ON_FAILURE,
                self._on_process_failure,
                priority=1,
                description="Failure handling and recovery initiation"
            )
            
            self.logger.info("Lifecycle hooks configured successfully")
            
        except Exception as e:
            self.logger.error(f"Error setting up lifecycle hooks: {e}")
    
    def _setup_performance_callbacks(self):
        """Настройка performance callbacks для мониторинга и оптимизации"""
        try:
            # Callback для оптимизации
            self.performance_optimizer.add_optimization_callback(self._on_optimization_applied)
            
            # Callback для конфигурационных изменений
            self.configuration_manager.add_change_listener(self._on_configuration_change)
            
            self.logger.info("Performance callbacks configured successfully")
            
        except Exception as e:
            self.logger.error(f"Error setting up performance callbacks: {e}")
    
    async def _on_before_start(self, process_id: str, context: Dict):
        """Hook вызываемый перед запуском процесса"""
        try:
            # Создание конфигурации бота в Configuration Manager
            await self.configuration_manager.create_bot_configuration(
                bot_id=process_id,
                bot_type="telegram_bot",
                initial_config=context.get('bot_config', {})
            )
            
            # Выделение ресурсов
            await self.resource_allocator.allocate_resources(
                process_id=process_id,
                priority=ResourcePriority.NORMAL
            )
            
            self.logger.debug(f"Pre-start setup completed for process {process_id}")
            
        except Exception as e:
            self.logger.error(f"Error in before_start hook for {process_id}: {e}")
    
    async def _on_after_start(self, process_id: str, context: Dict):
        """Hook вызываемый после запуска процесса"""
        try:
            # Регистрация в performance optimizer
            self.performance_optimizer.register_process(process_id)
            
            # Добавление мониторинга ресурсов
            pid = context.get('pid')
            if pid:
                self.resource_allocator.add_process_monitoring(process_id, pid)
            
            self.logger.debug(f"Post-start setup completed for process {process_id}")
            
        except Exception as e:
            self.logger.error(f"Error in after_start hook for {process_id}: {e}")
    
    async def _on_before_stop(self, process_id: str, context: Dict):
        """Hook вызываемый перед остановкой процесса"""
        try:
            # Graceful shutdown notification
            self.logger.info(f"Preparing graceful shutdown for process {process_id}")
            
        except Exception as e:
            self.logger.error(f"Error in before_stop hook for {process_id}: {e}")
    
    async def _on_after_stop(self, process_id: str, context: Dict):
        """Hook вызываемый после остановки процесса"""
        try:
            # Освобождение ресурсов
            await self.resource_allocator.deallocate_resources(process_id)
            
            # Удаление из performance optimizer
            self.performance_optimizer.unregister_process(process_id)
            
            self.logger.debug(f"Post-stop cleanup completed for process {process_id}")
            
        except Exception as e:
            self.logger.error(f"Error in after_stop hook for {process_id}: {e}")
    
    async def _on_process_failure(self, process_id: str, context: Dict):
        """Hook вызываемый при ошибке процесса"""
        try:
            error = context.get('error', 'Unknown error')
            self.logger.warning(f"Process {process_id} failed: {error}")
            
            # Добавление метрики ошибки
            self.performance_optimizer.add_metric(
                process_id=process_id,
                metric_type=MetricType.ERROR_RATE,
                value=1.0
            )
            
        except Exception as e:
            self.logger.error(f"Error in failure hook for {process_id}: {e}")
    
    async def _on_optimization_applied(self, action):
        """Callback для применения оптимизации"""
        try:
            self.logger.info(f"Optimization applied: {action.action_type} for process {action.process_id}")
            
        except Exception as e:
            self.logger.error(f"Error in optimization callback: {e}")
    
    async def _on_configuration_change(self, bot_id: str, change_type: str, details: Dict):
        """Callback для изменения конфигурации"""
        try:
            self.logger.info(f"Configuration {change_type} for bot {bot_id}: {details}")
            
            # Reload bot configuration if needed
            if change_type == "updated" and bot_id in self.bot_processes:
                # Trigger configuration reload
                await self._reload_bot_configuration(bot_id)
            
        except Exception as e:
            self.logger.error(f"Error in configuration change callback: {e}")
    
    async def _reload_bot_configuration(self, bot_id: str):
        """Перезагрузка конфигурации бота"""
        try:
            # Получение обновленной конфигурации
            updated_config = await self.configuration_manager.get_bot_configuration(bot_id)
            
            if updated_config and bot_id in self.bot_processes:
                # Применение новой конфигурации
                merged_config = updated_config.get_merged_config()
                self.logger.info(f"Reloaded configuration for bot {bot_id}")
                
        except Exception as e:
            self.logger.error(f"Error reloading configuration for bot {bot_id}: {e}")
    
    async def _load_bot_configurations(self):
        """Загрузка конфигураций ботов из базы данных"""
        try:
            # TODO: Интеграция с database layer из Phase 1
            # Пока используем конфигурацию по умолчанию
            default_config = BotConfiguration(
                bot_id="default_bot",
                bot_token=self.config.telegram.bot_token,
                database_role="bot_default",
                max_memory_mb=512,
                max_connections=10
            )
            
            self.bot_configurations["default_bot"] = default_config
            self.logger.info(f"Loaded {len(self.bot_configurations)} bot configurations")
            
        except Exception as e:
            self.logger.error(f"Error loading bot configurations: {e}")
            raise
    
    async def _auto_start_bots(self):
        """Автоматический запуск ботов при старте"""
        for bot_id, config in self.bot_configurations.items():
            if config.restart_policy in ["always", "on-failure"]:
                await self.create_bot(bot_id, config)
                await self.start_bot(bot_id)
    
    async def create_bot(self, bot_id: str, config: BotConfiguration) -> bool:
        """
        Создание нового bot process
        
        Args:
            bot_id: Уникальный идентификатор бота
            config: Конфигурация бота
            
        Returns:
            bool: True если бот создан успешно
        """
        try:
            if bot_id in self.bot_processes:
                self.logger.warning(f"Bot {bot_id} already exists")
                return False
            
            # Проверка ресурсных ограничений
            if not await self._check_resource_limits():
                self.logger.error("Resource limits exceeded, cannot create new bot")
                return False
            
            # Создание BotProcess
            bot_process = BotProcess(
                bot_id=bot_id,
                config=config,
                ipc_manager=self.ipc_manager,
                logger=self.logger
            )
            
            self.bot_processes[bot_id] = bot_process
            self.bot_configurations[bot_id] = config
            
            # Регистрация в мониторе
            self.process_monitor.register_bot(bot_id, bot_process)
            
            self.logger.info(f"Bot {bot_id} created successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating bot {bot_id}: {e}")
            return False
    
    async def start_bot(self, bot_id: str) -> bool:
        """
        Запуск bot process
        
        Args:
            bot_id: Идентификатор бота
            
        Returns:
            bool: True если бот запущен успешно
        """
        try:
            if bot_id not in self.bot_processes:
                self.logger.error(f"Bot {bot_id} not found")
                return False
            
            bot_process = self.bot_processes[bot_id]
            
            # Запуск процесса
            success = await bot_process.start()
            
            if success:
                self.logger.info(f"Bot {bot_id} started successfully (PID: {bot_process.pid})")
                
                # Запуск мониторинга для этого бота
                await self.process_monitor.start_monitoring(bot_id)
                
                return True
            else:
                self.logger.error(f"Failed to start bot {bot_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting bot {bot_id}: {e}")
            return False
    
    async def stop_bot(self, bot_id: str, graceful: bool = True) -> bool:
        """
        Остановка bot process
        
        Args:
            bot_id: Идентификатор бота
            graceful: Graceful shutdown или принудительное завершение
            
        Returns:
            bool: True если бот остановлен успешно
        """
        try:
            if bot_id not in self.bot_processes:
                self.logger.error(f"Bot {bot_id} not found")
                return False
            
            bot_process = self.bot_processes[bot_id]
            
            # Остановка мониторинга
            await self.process_monitor.stop_monitoring(bot_id)
            
            # Остановка процесса
            success = await bot_process.stop(graceful=graceful)
            
            if success:
                self.logger.info(f"Bot {bot_id} stopped successfully")
                return True
            else:
                self.logger.error(f"Failed to stop bot {bot_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error stopping bot {bot_id}: {e}")
            return False
    
    async def restart_bot(self, bot_id: str) -> bool:
        """
        Перезапуск bot process
        
        Args:
            bot_id: Идентификатор бота
            
        Returns:
            bool: True если бот перезапущен успешно
        """
        try:
            self.logger.info(f"Restarting bot {bot_id}")
            
            # Graceful stop
            await self.stop_bot(bot_id, graceful=True)
            
            # Пауза перед запуском
            await asyncio.sleep(2)
            
            # Запуск
            success = await self.start_bot(bot_id)
            
            if success:
                self.logger.info(f"Bot {bot_id} restarted successfully")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error restarting bot {bot_id}: {e}")
            return False
    
    async def destroy_bot(self, bot_id: str) -> bool:
        """
        Полное удаление bot process
        
        Args:
            bot_id: Идентификатор бота
            
        Returns:
            bool: True если бот удален успешно
        """
        try:
            if bot_id not in self.bot_processes:
                self.logger.error(f"Bot {bot_id} not found")
                return False
            
            # Остановка если запущен
            if self.bot_processes[bot_id].state != BotProcessState.STOPPED:
                await self.stop_bot(bot_id, graceful=True)
            
            # Удаление из мониторинга
            self.process_monitor.unregister_bot(bot_id)
            
            # Удаление из структур
            del self.bot_processes[bot_id]
            del self.bot_configurations[bot_id]
            
            self.logger.info(f"Bot {bot_id} destroyed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error destroying bot {bot_id}: {e}")
            return False
    
    async def _check_resource_limits(self) -> bool:
        """Проверка ресурсных ограничений"""
        try:
            # Проверка количества ботов
            if len(self.bot_processes) >= self.resource_limits['max_concurrent_bots']:
                return False
            
            # Проверка использования памяти
            memory_usage = sum(
                process.memory_usage_mb 
                for process in self.bot_processes.values()
                if process.state == BotProcessState.RUNNING
            )
            
            if memory_usage >= self.resource_limits['max_total_memory_mb']:
                return False
            
            # Проверка CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent >= self.resource_limits['max_cpu_percent']:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking resource limits: {e}")
            return False
    
    async def _main_monitoring_loop(self):
        """Основной цикл мониторинга ProcessSupervisor"""
        self.logger.info("Starting main monitoring loop")
        
        while self.state == ProcessSupervisorState.RUNNING:
            try:
                # Проверка состояния ботов
                await self._health_check_bots()
                
                # Обработка IPC сообщений
                await self.ipc_manager.process_messages()
                
                # Сборка метрик
                await self._collect_metrics()
                
                # Ожидание перед следующей итерацией
                await asyncio.sleep(10)  # 10 секунд между проверками
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)
    
    async def _health_check_bots(self):
        """Health check всех ботов"""
        for bot_id, bot_process in self.bot_processes.items():
            try:
                health_status = await bot_process.health_check()
                
                if not health_status and bot_process.state == BotProcessState.RUNNING:
                    config = self.bot_configurations[bot_id]
                    if config.restart_policy in ["always", "on-failure"]:
                        self.logger.warning(f"Bot {bot_id} health check failed, restarting")
                        await self.restart_bot(bot_id)
                        
            except Exception as e:
                self.logger.error(f"Error health checking bot {bot_id}: {e}")
    
    async def _collect_metrics(self):
        """Сбор метрик системы"""
        try:
            metrics = {
                'timestamp': time.time(),
                'supervisor_state': self.state.value,
                'total_bots': len(self.bot_processes),
                'running_bots': len([
                    p for p in self.bot_processes.values() 
                    if p.state == BotProcessState.RUNNING
                ]),
                'total_memory_mb': sum(
                    p.memory_usage_mb for p in self.bot_processes.values()
                    if p.state == BotProcessState.RUNNING
                ),
                'cpu_percent': psutil.cpu_percent()
            }
            
            # TODO: Интеграция с metrics system
            self.logger.debug(f"System metrics: {metrics}")
            
        except Exception as e:
            self.logger.error(f"Error collecting metrics: {e}")
    
    async def get_status(self) -> Dict:
        """Получение статуса ProcessSupervisor"""
        bot_statuses = {}
        for bot_id, bot_process in self.bot_processes.items():
            bot_statuses[bot_id] = {
                'state': bot_process.state.value,
                'pid': bot_process.pid,
                'memory_usage_mb': bot_process.memory_usage_mb,
                'uptime_seconds': bot_process.uptime_seconds,
                'last_health_check': bot_process.last_health_check
            }
        
        return {
            'supervisor_state': self.state.value,
            'total_bots': len(self.bot_processes),
            'running_bots': len([
                p for p in self.bot_processes.values() 
                if p.state == BotProcessState.RUNNING
            ]),
            'bots': bot_statuses,
            'resource_usage': {
                'total_memory_mb': sum(
                    p.memory_usage_mb for p in self.bot_processes.values()
                ),
                'cpu_percent': psutil.cpu_percent()
            }
        }
    
    async def shutdown(self):
        """Graceful shutdown ProcessSupervisor with Phase 2B components"""
        try:
            self.logger.info("Starting ProcessSupervisor shutdown with Phase 2B components")
            self.state = ProcessSupervisorState.SHUTTING_DOWN
            
            # Остановка всех ботов
            shutdown_tasks = []
            for bot_id in list(self.bot_processes.keys()):
                task = asyncio.create_task(self.stop_bot(bot_id, graceful=True))
                shutdown_tasks.append(task)
            
            # Ожидание завершения всех ботов
            if shutdown_tasks:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=30  # 30 секунд на graceful shutdown
                )
            
            # Остановка Phase 2B компонентов
            await self.performance_optimizer.stop()
            await self.lifecycle_manager.stop()
            await self.resource_allocator.stop()
            await self.configuration_manager.stop()
            
            # Остановка Phase 2A компонентов
            await self.process_monitor.stop()
            await self.ipc_manager.stop()
            
            self.state = ProcessSupervisorState.STOPPED
            self.logger.info("ProcessSupervisor shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            self.state = ProcessSupervisorState.ERROR


# Функция для запуска ProcessSupervisor
async def run_multibot_manager(config: Config):
    """
    Точка входа для запуска MultiBotManager в ProcessSupervisor режиме
    
    Args:
        config: Конфигурация системы
    """
    manager = MultiBotManager(config)
    
    try:
        await manager.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"Fatal error in MultiBotManager: {e}")
        raise
    finally:
        await manager.shutdown()


if __name__ == "__main__":
    # Прямой запуск для тестирования
    import sys
    from src.config.config import Config
    
    config = Config()
    
    try:
        asyncio.run(run_multibot_manager(config))
    except KeyboardInterrupt:
        print("\nProcessSupervisor stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
