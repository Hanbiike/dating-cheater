"""
Bot Runner - Entry point for individual bot processes

Скрипт запуска отдельного экземпляра Telegram бота в изолированном процессе.
Обеспечивает инициализацию всех компонентов бота, IPC communication с 
ProcessSupervisor и graceful shutdown handling.

Запускается ProcessSupervisor для каждого отдельного бота.
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

# Добавление корневого пути в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from src.config.config import Config
from src.utils.logger import setup_logger
from src.core.connection_manager import ConnectionManager
from src.core.girls_manager import GirlsManager
from src.core.response_generator import ResponseGenerator
from src.core.autonomous_manager import AutonomousManager
from src.utils.metrics import MetricsCollector
from src.processsupervisor.communication.ipc_communication import IPCManager, IPCMessage, MessageType


class BotRunner:
    """
    Bot Runner - обертка для запуска отдельного бота в процессе
    
    Функции:
    - Инициализация всех компонентов бота
    - IPC communication с ProcessSupervisor
    - Health monitoring и status reporting
    - Graceful shutdown handling
    - Error recovery и restart logic
    """
    
    def __init__(self, bot_id: str, bot_config: dict):
        self.bot_id = bot_id
        self.bot_config = bot_config
        self.config = Config()
        
        # Обновление конфигурации из переданных параметров
        self._update_config()
        
        # Логгер для этого экземпляра
        self.logger = setup_logger(f"bot.{bot_id}")
        
        # IPC Manager
        self.ipc_manager = IPCManager()
        
        # Компоненты бота
        self.connection_manager = None
        self.girls_manager = None
        self.response_generator = None
        self.autonomous_manager = None
        self.metrics = None
        
        # Состояние
        self.is_running = False
        self.start_time = time.time()
        self.shutdown_event = asyncio.Event()
        
        # Статистика
        self.stats = {
            'messages_processed': 0,
            'errors_count': 0,
            'last_activity': time.time(),
            'uptime_start': time.time()
        }
        
        # Настройка сигналов
        self._setup_signal_handlers()
        
        self.logger.info(f"BotRunner initialized for bot {bot_id}")
    
    def _update_config(self):
        """Обновление конфигурации из параметров бота"""
        # Обновление Telegram токена
        self.config.telegram.bot_token = self.bot_config['bot_token']
        
        # Обновление database настроек
        if hasattr(self.config, 'database'):
            # TODO: Интеграция с database role из Phase 1
            pass
        
        # Обновление прочих настроек
        # TODO: Добавить больше конфигурационных параметров
    
    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов завершения"""
        self.logger.info(f"Bot {self.bot_id} received signal {signum}, shutting down")
        asyncio.create_task(self.shutdown())
    
    async def start(self):
        """Запуск бота"""
        try:
            self.logger.info(f"Starting bot {self.bot_id}")
            
            # Инициализация IPC
            await self.ipc_manager.start()
            await self.ipc_manager.create_channel(self.bot_id)
            
            # Регистрация IPC handlers
            self._register_ipc_handlers()
            
            # Инициализация компонентов
            await self._initialize_components()
            
            # Запуск компонентов
            await self._start_components()
            
            self.is_running = True
            self.logger.info(f"Bot {self.bot_id} started successfully")
            
            # Уведомление ProcessSupervisor о готовности
            await self._notify_supervisor_ready()
            
            # Основной цикл
            await self._main_loop()
            
        except Exception as e:
            self.logger.error(f"Error starting bot {self.bot_id}: {e}")
            await self.shutdown()
            raise
    
    async def _initialize_components(self):
        """Инициализация компонентов бота"""
        try:
            # Connection Manager
            self.connection_manager = ConnectionManager(self.config)
            
            # Girls Manager
            self.girls_manager = GirlsManager(self.config)
            
            # Response Generator
            self.response_generator = ResponseGenerator(self.config)
            
            # Autonomous Manager
            self.autonomous_manager = AutonomousManager(
                self.config,
                self.connection_manager,
                self.girls_manager,
                self.response_generator
            )
            
            # Metrics
            self.metrics = MetricsCollector()
            
            self.logger.info(f"Components initialized for bot {self.bot_id}")
            
        except Exception as e:
            self.logger.error(f"Error initializing components for bot {self.bot_id}: {e}")
            raise
    
    async def _start_components(self):
        """Запуск компонентов бота"""
        try:
            # Запуск в правильном порядке
            await self.connection_manager.start()
            await self.girls_manager.initialize()
            await self.response_generator.initialize()
            await self.autonomous_manager.start()
            
            self.logger.info(f"Components started for bot {self.bot_id}")
            
        except Exception as e:
            self.logger.error(f"Error starting components for bot {self.bot_id}: {e}")
            raise
    
    def _register_ipc_handlers(self):
        """Регистрация обработчиков IPC команд"""
        self.ipc_manager.register_handler(self.bot_id, 'ping', self._handle_ping)
        self.ipc_manager.register_handler(self.bot_id, 'status', self._handle_status)
        self.ipc_manager.register_handler(self.bot_id, 'shutdown', self._handle_shutdown)
        self.ipc_manager.register_handler(self.bot_id, 'heartbeat', self._handle_heartbeat)
        self.ipc_manager.register_handler(self.bot_id, 'metrics', self._handle_metrics)
        self.ipc_manager.register_handler(self.bot_id, 'restart_component', self._handle_restart_component)
    
    async def _handle_ping(self, message: IPCMessage) -> dict:
        """Обработка ping команды"""
        return {
            'status': 'ok',
            'bot_id': self.bot_id,
            'timestamp': time.time(),
            'uptime': time.time() - self.start_time
        }
    
    async def _handle_status(self, message: IPCMessage) -> dict:
        """Обработка status команды"""
        return {
            'bot_id': self.bot_id,
            'is_running': self.is_running,
            'uptime': time.time() - self.start_time,
            'stats': self.stats,
            'components': {
                'connection_manager': bool(self.connection_manager),
                'girls_manager': bool(self.girls_manager),
                'response_generator': bool(self.response_generator),
                'autonomous_manager': bool(self.autonomous_manager)
            }
        }
    
    async def _handle_shutdown(self, message: IPCMessage) -> dict:
        """Обработка shutdown команды"""
        graceful = message.data.get('graceful', True)
        
        self.logger.info(f"Received shutdown command (graceful={graceful})")
        
        # Запуск shutdown в фоне
        asyncio.create_task(self.shutdown(graceful=graceful))
        
        return {
            'status': 'shutting_down',
            'graceful': graceful
        }
    
    async def _handle_heartbeat(self, message: IPCMessage) -> dict:
        """Обработка heartbeat"""
        return {
            'status': 'alive',
            'bot_id': self.bot_id,
            'timestamp': time.time(),
            'last_activity': self.stats['last_activity']
        }
    
    async def _handle_metrics(self, message: IPCMessage) -> dict:
        """Обработка запроса метрик"""
        if self.metrics:
            return self.metrics.get_current_metrics_dict()
        else:
            return {'error': 'metrics not available'}
    
    async def _handle_restart_component(self, message: IPCMessage) -> dict:
        """Обработка перезапуска компонента"""
        component_name = message.data.get('component')
        
        if component_name == 'autonomous_manager' and self.autonomous_manager:
            try:
                await self.autonomous_manager.restart()
                return {'status': 'restarted', 'component': component_name}
            except Exception as e:
                return {'status': 'error', 'error': str(e)}
        
        return {'status': 'unknown_component', 'component': component_name}
    
    async def _notify_supervisor_ready(self):
        """Уведомление ProcessSupervisor о готовности"""
        try:
            response = await self.ipc_manager.send_message('supervisor', {
                'command': 'bot_ready',
                'data': {
                    'bot_id': self.bot_id,
                    'timestamp': time.time(),
                    'pid': os.getpid()
                }
            })
            
            if response:
                self.logger.info("Notified supervisor about readiness")
            else:
                self.logger.warning("Failed to notify supervisor")
                
        except Exception as e:
            self.logger.error(f"Error notifying supervisor: {e}")
    
    async def _main_loop(self):
        """Основной цикл бота"""
        self.logger.info(f"Starting main loop for bot {self.bot_id}")
        
        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Обработка IPC сообщений
                await self.ipc_manager.process_messages()
                
                # Основная логика бота (автономный режим)
                if self.autonomous_manager:
                    await self.autonomous_manager.process_cycle()
                
                # Обновление статистики
                self.stats['last_activity'] = time.time()
                
                # Пауза между итерациями
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in main loop for bot {self.bot_id}: {e}")
                self.stats['errors_count'] += 1
                await asyncio.sleep(5)  # Пауза при ошибке
    
    async def shutdown(self, graceful: bool = True):
        """Остановка бота"""
        try:
            self.logger.info(f"Shutting down bot {self.bot_id} (graceful={graceful})")
            self.is_running = False
            self.shutdown_event.set()
            
            if graceful:
                # Graceful shutdown компонентов
                if self.autonomous_manager:
                    await self.autonomous_manager.stop()
                
                if self.connection_manager:
                    await self.connection_manager.stop()
                
                # Финальное уведомление supervisor
                try:
                    await self.ipc_manager.send_message('supervisor', {
                        'command': 'bot_stopped',
                        'data': {
                            'bot_id': self.bot_id,
                            'timestamp': time.time(),
                            'stats': self.stats
                        }
                    })
                except:
                    pass  # Ignore IPC errors during shutdown
            
            # Остановка IPC
            await self.ipc_manager.stop()
            
            self.logger.info(f"Bot {self.bot_id} shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown of bot {self.bot_id}: {e}")


async def main():
    """Точка входа для bot runner"""
    parser = argparse.ArgumentParser(description='Multi-Bot Runner - Individual Bot Process')
    parser.add_argument('--bot-id', required=True, help='Unique bot identifier')
    parser.add_argument('--config', required=True, help='Bot configuration (JSON string)')
    
    args = parser.parse_args()
    
    try:
        # Парсинг конфигурации
        bot_config = json.loads(args.config)
        
        # Создание и запуск бота
        bot_runner = BotRunner(args.bot_id, bot_config)
        await bot_runner.start()
        
    except KeyboardInterrupt:
        print(f"Bot {args.bot_id} interrupted by user")
    except Exception as e:
        print(f"Error running bot {args.bot_id}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Настройка логирования для отдельного процесса
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Запуск бота
    asyncio.run(main())
