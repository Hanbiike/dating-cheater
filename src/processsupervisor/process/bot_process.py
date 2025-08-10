"""
Bot Process Wrapper - Individual bot process management

Обертка для управления отдельными экземплярами Telegram ботов в изолированных процессах.
Предоставляет интерфейс для lifecycle management, health monitoring и IPC communication.

Функции:
- Запуск и остановка bot процессов
- Health monitoring и status reporting
- IPC communication с ProcessSupervisor
- Resource monitoring (memory, CPU)
- Graceful shutdown handling
"""

import asyncio
import json
import logging
import os
import psutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class BotProcessState(Enum):
    """Состояния bot process"""
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    CRASHED = "crashed"


@dataclass
class ProcessHealth:
    """Информация о здоровье процесса"""
    is_alive: bool
    memory_usage_mb: float
    cpu_percent: float
    uptime_seconds: float
    last_response_time: Optional[float]
    error_count: int = 0


class BotProcess:
    """
    Wrapper для управления отдельным bot process
    
    Обеспечивает:
    - Process lifecycle management
    - Health monitoring
    - Resource tracking
    - IPC communication
    - Error handling и recovery
    """
    
    def __init__(self, bot_id: str, config, ipc_manager, logger: logging.Logger):
        self.bot_id = bot_id
        self.config = config
        self.ipc_manager = ipc_manager
        self.logger = logger.getChild(f"bot.{bot_id}")
        
        # Process management
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.state = BotProcessState.CREATED
        
        # Health tracking
        self.start_time: Optional[float] = None
        self.last_health_check: Optional[float] = None
        self.health_info = ProcessHealth(
            is_alive=False,
            memory_usage_mb=0.0,
            cpu_percent=0.0,
            uptime_seconds=0.0,
            last_response_time=None
        )
        
        # Error tracking
        self.restart_count = 0
        self.last_restart_time: Optional[float] = None
        
        self.logger.info(f"BotProcess {bot_id} initialized")
    
    async def start(self) -> bool:
        """
        Запуск bot process
        
        Returns:
            bool: True если процесс запущен успешно
        """
        try:
            if self.state in [BotProcessState.RUNNING, BotProcessState.STARTING]:
                self.logger.warning(f"Bot {self.bot_id} already running or starting")
                return False
            
            self.logger.info(f"Starting bot process {self.bot_id}")
            self.state = BotProcessState.STARTING
            
            # Подготовка окружения
            env = await self._prepare_environment()
            
            # Создание команды запуска
            cmd = await self._build_start_command()
            
            # Запуск процесса
            self.process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                preexec_fn=os.setsid,  # Создание новой session group
                cwd=Path.cwd()
            )
            
            self.pid = self.process.pid
            self.start_time = time.time()
            
            # Ожидание успешного запуска
            startup_success = await self._wait_for_startup()
            
            if startup_success:
                self.state = BotProcessState.RUNNING
                self.logger.info(f"Bot {self.bot_id} started successfully (PID: {self.pid})")
                return True
            else:
                await self._cleanup_failed_start()
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting bot {self.bot_id}: {e}")
            self.state = BotProcessState.ERROR
            await self._cleanup_failed_start()
            return False
    
    async def stop(self, graceful: bool = True, timeout: int = 30) -> bool:
        """
        Остановка bot process
        
        Args:
            graceful: Graceful shutdown или принудительное завершение
            timeout: Таймаут для graceful shutdown
            
        Returns:
            bool: True если процесс остановлен успешно
        """
        try:
            if self.state in [BotProcessState.STOPPED, BotProcessState.STOPPING]:
                self.logger.warning(f"Bot {self.bot_id} already stopped or stopping")
                return True
            
            if not self.process or not self.pid:
                self.logger.warning(f"Bot {self.bot_id} process not found")
                self.state = BotProcessState.STOPPED
                return True
            
            self.logger.info(f"Stopping bot {self.bot_id} (graceful={graceful})")
            self.state = BotProcessState.STOPPING
            
            if graceful:
                # Graceful shutdown
                success = await self._graceful_shutdown(timeout)
                if success:
                    self.state = BotProcessState.STOPPED
                    return True
            
            # Принудительное завершение
            return await self._force_shutdown()
            
        except Exception as e:
            self.logger.error(f"Error stopping bot {self.bot_id}: {e}")
            return False
    
    async def health_check(self) -> bool:
        """
        Проверка здоровья bot process
        
        Returns:
            bool: True если процесс здоров
        """
        try:
            if not self.process or not self.pid:
                self.health_info.is_alive = False
                return False
            
            # Проверка что процесс еще существует
            if not psutil.pid_exists(self.pid):
                self.health_info.is_alive = False
                self.state = BotProcessState.CRASHED
                return False
            
            # Получение информации о процессе
            try:
                proc = psutil.Process(self.pid)
                
                # Проверка статуса
                if proc.status() == psutil.STATUS_ZOMBIE:
                    self.health_info.is_alive = False
                    self.state = BotProcessState.CRASHED
                    return False
                
                # Обновление метрик
                memory_info = proc.memory_info()
                self.health_info.memory_usage_mb = memory_info.rss / 1024 / 1024
                self.health_info.cpu_percent = proc.cpu_percent()
                
                if self.start_time:
                    self.health_info.uptime_seconds = time.time() - self.start_time
                
                self.health_info.is_alive = True
                self.last_health_check = time.time()
                
                # Проверка ресурсных лимитов
                if self.health_info.memory_usage_mb > self.config.max_memory_mb:
                    self.logger.warning(
                        f"Bot {self.bot_id} exceeds memory limit: "
                        f"{self.health_info.memory_usage_mb:.1f}MB > {self.config.max_memory_mb}MB"
                    )
                    return False
                
                return True
                
            except psutil.NoSuchProcess:
                self.health_info.is_alive = False
                self.state = BotProcessState.CRASHED
                return False
                
        except Exception as e:
            self.logger.error(f"Error checking health of bot {self.bot_id}: {e}")
            return False
    
    async def send_command(self, command: str, data: Dict = None) -> Optional[Dict]:
        """
        Отправка команды в bot process через IPC
        
        Args:
            command: Команда для выполнения
            data: Дополнительные данные
            
        Returns:
            Dict: Ответ от процесса или None при ошибке
        """
        try:
            if self.state != BotProcessState.RUNNING:
                self.logger.error(f"Cannot send command to bot {self.bot_id}: not running")
                return None
            
            message = {
                'command': command,
                'bot_id': self.bot_id,
                'data': data or {},
                'timestamp': time.time()
            }
            
            response = await self.ipc_manager.send_message(self.bot_id, message)
            return response
            
        except Exception as e:
            self.logger.error(f"Error sending command to bot {self.bot_id}: {e}")
            return None
    
    @property
    def memory_usage_mb(self) -> float:
        """Текущее использование памяти в MB"""
        return self.health_info.memory_usage_mb
    
    @property
    def uptime_seconds(self) -> float:
        """Время работы процесса в секундах"""
        return self.health_info.uptime_seconds
    
    async def _prepare_environment(self) -> Dict[str, str]:
        """Подготовка окружения для bot process"""
        env = os.environ.copy()
        
        # Базовые переменные
        env.update({
            'BOT_ID': self.bot_id,
            'BOT_TOKEN': self.config.bot_token,
            'DATABASE_ROLE': self.config.database_role,
            'MAX_MEMORY_MB': str(self.config.max_memory_mb),
            'MAX_CONNECTIONS': str(self.config.max_connections),
            'HEALTH_CHECK_INTERVAL': str(self.config.health_check_interval),
            'PYTHONPATH': str(Path.cwd()),
            'PYTHONUNBUFFERED': '1'  # Для немедленного вывода логов
        })
        
        # Пользовательские переменные
        env.update(self.config.environment_vars)
        
        return env
    
    async def _build_start_command(self) -> list:
        """Создание команды запуска bot process"""
        # Используем тот же Python интерпретатор
        python_exe = sys.executable
        
        # Скрипт запуска отдельного бота
        bot_script = Path.cwd() / "bot_runner.py"
        
        cmd = [
            python_exe,
            str(bot_script),
            '--bot-id', self.bot_id,
            '--config', json.dumps(self.config.to_dict())
        ]
        
        return cmd
    
    async def _wait_for_startup(self) -> bool:
        """Ожидание успешного запуска процесса"""
        timeout = self.config.startup_timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Проверка что процесс еще жив
            if self.process.poll() is not None:
                self.logger.error(f"Bot {self.bot_id} process exited during startup")
                return False
            
            # Проверка через health check
            if await self.health_check():
                # Дополнительная проверка через IPC
                response = await self.send_command('ping')
                if response and response.get('status') == 'ok':
                    return True
            
            await asyncio.sleep(1)
        
        self.logger.error(f"Bot {self.bot_id} startup timeout ({timeout}s)")
        return False
    
    async def _graceful_shutdown(self, timeout: int) -> bool:
        """Graceful shutdown процесса"""
        try:
            # Отправка команды graceful shutdown через IPC
            response = await self.send_command('shutdown', {'graceful': True})
            
            if response:
                # Ожидание завершения
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.process.poll() is not None:
                        self.logger.info(f"Bot {self.bot_id} gracefully shut down")
                        self.state = BotProcessState.STOPPED
                        return True
                    await asyncio.sleep(0.5)
            
            # Если IPC не сработал, пробуем SIGTERM
            self.logger.info(f"Sending SIGTERM to bot {self.bot_id}")
            os.killpg(os.getpgid(self.pid), signal.SIGTERM)
            
            # Ожидание после SIGTERM
            start_time = time.time()
            while time.time() - start_time < timeout // 2:
                if self.process.poll() is not None:
                    self.logger.info(f"Bot {self.bot_id} terminated with SIGTERM")
                    self.state = BotProcessState.STOPPED
                    return True
                await asyncio.sleep(0.5)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error during graceful shutdown of bot {self.bot_id}: {e}")
            return False
    
    async def _force_shutdown(self) -> bool:
        """Принудительное завершение процесса"""
        try:
            self.logger.warning(f"Force killing bot {self.bot_id}")
            
            # SIGKILL для всей process group
            os.killpg(os.getpgid(self.pid), signal.SIGKILL)
            
            # Ожидание завершения
            for _ in range(10):  # 5 секунд
                if self.process.poll() is not None:
                    self.logger.info(f"Bot {self.bot_id} force killed")
                    self.state = BotProcessState.STOPPED
                    return True
                await asyncio.sleep(0.5)
            
            self.logger.error(f"Failed to kill bot {self.bot_id}")
            return False
            
        except Exception as e:
            self.logger.error(f"Error force killing bot {self.bot_id}: {e}")
            return False
    
    async def _cleanup_failed_start(self):
        """Очистка после неудачного запуска"""
        try:
            if self.process:
                if self.process.poll() is None:
                    # Процесс еще жив, убиваем
                    try:
                        os.killpg(os.getpgid(self.pid), signal.SIGKILL)
                    except:
                        pass
                
                self.process = None
                self.pid = None
            
            self.state = BotProcessState.ERROR
            
        except Exception as e:
            self.logger.error(f"Error cleaning up failed start of bot {self.bot_id}: {e}")


# Вспомогательный класс для создания bot processes
class BotProcessFactory:
    """Factory для создания BotProcess instances"""
    
    @staticmethod
    def create_bot_process(bot_id: str, config, ipc_manager, logger: logging.Logger) -> BotProcess:
        """
        Создание нового BotProcess
        
        Args:
            bot_id: Идентификатор бота
            config: Конфигурация бота
            ipc_manager: IPC manager
            logger: Logger
            
        Returns:
            BotProcess: Новый экземпляр процесса
        """
        return BotProcess(bot_id, config, ipc_manager, logger)
