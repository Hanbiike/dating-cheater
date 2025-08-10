"""
Process Monitor - Health monitoring system for bot processes

Система мониторинга здоровья и производительности bot processes в real-time.
Предоставляет автоматический health checking, performance tracking, error detection
и automatic recovery capabilities.

Функции:
- Real-time health monitoring всех bot processes
- Performance metrics collection (CPU, memory, response time)
- Automatic failure detection и recovery
- Alerting и notification system
- Historical data tracking
- Resource usage optimization
"""

import asyncio
import logging
import psutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import json
from pathlib import Path


class HealthStatus(Enum):
    """Статусы здоровья процесса"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    """Уровни алертов"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ProcessMetrics:
    """Метрики производительности процесса"""
    bot_id: str
    timestamp: float
    
    # System metrics
    cpu_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_percent: float = 0.0
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_io_sent_mb: float = 0.0
    network_io_recv_mb: float = 0.0
    
    # Process metrics
    thread_count: int = 0
    file_descriptors: int = 0
    connections_count: int = 0
    
    # Application metrics
    response_time_ms: float = 0.0
    error_rate: float = 0.0
    message_count: int = 0
    uptime_seconds: float = 0.0
    
    def to_dict(self) -> Dict:
        """Конвертация в словарь"""
        return {
            'bot_id': self.bot_id,
            'timestamp': self.timestamp,
            'cpu_percent': self.cpu_percent,
            'memory_usage_mb': self.memory_usage_mb,
            'memory_percent': self.memory_percent,
            'disk_io_read_mb': self.disk_io_read_mb,
            'disk_io_write_mb': self.disk_io_write_mb,
            'network_io_sent_mb': self.network_io_sent_mb,
            'network_io_recv_mb': self.network_io_recv_mb,
            'thread_count': self.thread_count,
            'file_descriptors': self.file_descriptors,
            'connections_count': self.connections_count,
            'response_time_ms': self.response_time_ms,
            'error_rate': self.error_rate,
            'message_count': self.message_count,
            'uptime_seconds': self.uptime_seconds
        }


@dataclass
class HealthCheckResult:
    """Результат health check"""
    bot_id: str
    timestamp: float
    status: HealthStatus
    metrics: ProcessMetrics
    alerts: List[Dict] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def add_alert(self, level: AlertLevel, message: str, metric: str = None):
        """Добавление алерта"""
        self.alerts.append({
            'level': level.value,
            'message': message,
            'metric': metric,
            'timestamp': time.time()
        })
    
    def add_recommendation(self, message: str):
        """Добавление рекомендации"""
        self.recommendations.append(message)


class ThresholdManager:
    """Менеджер пороговых значений для алертов"""
    
    def __init__(self):
        self.thresholds = {
            # CPU thresholds
            'cpu_warning': 70.0,
            'cpu_critical': 90.0,
            
            # Memory thresholds (MB)
            'memory_warning_mb': 400,
            'memory_critical_mb': 500,
            'memory_warning_percent': 80.0,
            'memory_critical_percent': 95.0,
            
            # Response time thresholds (ms)
            'response_time_warning': 5000,
            'response_time_critical': 10000,
            
            # Error rate thresholds (%)
            'error_rate_warning': 5.0,
            'error_rate_critical': 10.0,
            
            # Connection thresholds
            'connections_warning': 8,
            'connections_critical': 10,
            
            # File descriptor thresholds
            'fd_warning': 100,
            'fd_critical': 200,
            
            # Uptime thresholds (seconds)
            'uptime_min_healthy': 60
        }
    
    def get_threshold(self, metric: str, level: str) -> Optional[float]:
        """Получение порогового значения"""
        key = f"{metric}_{level}"
        return self.thresholds.get(key)
    
    def update_threshold(self, metric: str, level: str, value: float):
        """Обновление порогового значения"""
        key = f"{metric}_{level}"
        self.thresholds[key] = value
    
    def check_threshold(self, metric_name: str, value: float) -> Optional[AlertLevel]:
        """Проверка значения против порогов"""
        critical_threshold = self.get_threshold(metric_name, 'critical')
        warning_threshold = self.get_threshold(metric_name, 'warning')
        
        if critical_threshold and value >= critical_threshold:
            return AlertLevel.CRITICAL
        elif warning_threshold and value >= warning_threshold:
            return AlertLevel.WARNING
        
        return None


class ProcessMonitor:
    """
    Process Monitor - система мониторинга bot processes
    
    Основные функции:
    - Continuous health monitoring всех зарегистрированных ботов
    - Performance metrics collection и analysis
    - Automatic alerting на основе thresholds
    - Recovery recommendations и automatic actions
    - Historical data storage и trending
    """
    
    def __init__(self, monitoring_interval: int = 30):
        self.monitoring_interval = monitoring_interval
        self.logger = logging.getLogger(__name__)
        
        # Registered bots
        self.monitored_bots: Dict[str, Any] = {}  # bot_id -> BotProcess
        
        # Monitoring state
        self.is_monitoring = False
        self.monitoring_tasks: List[asyncio.Task] = []
        
        # Threshold management
        self.threshold_manager = ThresholdManager()
        
        # Metrics storage
        self.metrics_history: Dict[str, List[ProcessMetrics]] = {}
        self.max_history_entries = 1000  # Максимум записей в истории
        
        # Health check results
        self.last_health_checks: Dict[str, HealthCheckResult] = {}
        
        # Alert handlers
        self.alert_handlers: List[Callable] = []
        
        # Performance tracking
        self.performance_baseline: Dict[str, Dict] = {}
        
        self.logger.info("ProcessMonitor initialized")
    
    async def start(self):
        """Запуск мониторинга"""
        try:
            self.logger.info("Starting ProcessMonitor")
            self.is_monitoring = True
            
            # Запуск задач мониторинга
            self.monitoring_tasks = [
                asyncio.create_task(self._monitoring_loop()),
                asyncio.create_task(self._metrics_cleanup_loop()),
                asyncio.create_task(self._performance_analysis_loop())
            ]
            
            self.logger.info("ProcessMonitor started successfully")
            
        except Exception as e:
            self.logger.error(f"Error starting ProcessMonitor: {e}")
            raise
    
    async def stop(self):
        """Остановка мониторинга"""
        try:
            self.logger.info("Stopping ProcessMonitor")
            self.is_monitoring = False
            
            # Остановка задач
            for task in self.monitoring_tasks:
                task.cancel()
            
            if self.monitoring_tasks:
                await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
            
            self.monitoring_tasks.clear()
            
            self.logger.info("ProcessMonitor stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping ProcessMonitor: {e}")
    
    def register_bot(self, bot_id: str, bot_process):
        """Регистрация бота для мониторинга"""
        try:
            self.monitored_bots[bot_id] = bot_process
            self.metrics_history[bot_id] = []
            
            self.logger.info(f"Registered bot {bot_id} for monitoring")
            
        except Exception as e:
            self.logger.error(f"Error registering bot {bot_id}: {e}")
    
    def unregister_bot(self, bot_id: str):
        """Отмена регистрации бота"""
        try:
            if bot_id in self.monitored_bots:
                del self.monitored_bots[bot_id]
            
            if bot_id in self.metrics_history:
                del self.metrics_history[bot_id]
            
            if bot_id in self.last_health_checks:
                del self.last_health_checks[bot_id]
            
            if bot_id in self.performance_baseline:
                del self.performance_baseline[bot_id]
            
            self.logger.info(f"Unregistered bot {bot_id} from monitoring")
            
        except Exception as e:
            self.logger.error(f"Error unregistering bot {bot_id}: {e}")
    
    async def start_monitoring(self, bot_id: str):
        """Запуск мониторинга конкретного бота"""
        if bot_id in self.monitored_bots:
            self.logger.info(f"Started monitoring for bot {bot_id}")
        else:
            self.logger.warning(f"Bot {bot_id} not registered for monitoring")
    
    async def stop_monitoring(self, bot_id: str):
        """Остановка мониторинга конкретного бота"""
        if bot_id in self.monitored_bots:
            self.logger.info(f"Stopped monitoring for bot {bot_id}")
        else:
            self.logger.warning(f"Bot {bot_id} not registered for monitoring")
    
    async def collect_metrics(self, bot_id: str) -> Optional[ProcessMetrics]:
        """Сбор метрик для конкретного бота"""
        try:
            if bot_id not in self.monitored_bots:
                return None
            
            bot_process = self.monitored_bots[bot_id]
            
            # Проверка что процесс существует
            if not bot_process.pid or not psutil.pid_exists(bot_process.pid):
                return None
            
            proc = psutil.Process(bot_process.pid)
            
            # Системные метрики
            cpu_percent = proc.cpu_percent()
            memory_info = proc.memory_info()
            memory_usage_mb = memory_info.rss / 1024 / 1024
            memory_percent = proc.memory_percent()
            
            # I/O метрики
            try:
                io_counters = proc.io_counters()
                disk_io_read_mb = io_counters.read_bytes / 1024 / 1024
                disk_io_write_mb = io_counters.write_bytes / 1024 / 1024
            except (psutil.AccessDenied, AttributeError):
                disk_io_read_mb = disk_io_write_mb = 0.0
            
            # Network I/O (приблизительно через system-wide stats)
            try:
                net_io = psutil.net_io_counters()
                network_io_sent_mb = net_io.bytes_sent / 1024 / 1024
                network_io_recv_mb = net_io.bytes_recv / 1024 / 1024
            except AttributeError:
                network_io_sent_mb = network_io_recv_mb = 0.0
            
            # Process specific metrics
            thread_count = proc.num_threads()
            
            try:
                file_descriptors = proc.num_fds() if hasattr(proc, 'num_fds') else 0
            except (psutil.AccessDenied, AttributeError):
                file_descriptors = 0
            
            try:
                connections_count = len(proc.connections())
            except (psutil.AccessDenied, AttributeError):
                connections_count = 0
            
            # Application metrics (от bot_process)
            uptime_seconds = bot_process.uptime_seconds
            
            # TODO: Получение application-specific metrics через IPC
            response_time_ms = 0.0  # Placeholder
            error_rate = 0.0  # Placeholder
            message_count = 0  # Placeholder
            
            metrics = ProcessMetrics(
                bot_id=bot_id,
                timestamp=time.time(),
                cpu_percent=cpu_percent,
                memory_usage_mb=memory_usage_mb,
                memory_percent=memory_percent,
                disk_io_read_mb=disk_io_read_mb,
                disk_io_write_mb=disk_io_write_mb,
                network_io_sent_mb=network_io_sent_mb,
                network_io_recv_mb=network_io_recv_mb,
                thread_count=thread_count,
                file_descriptors=file_descriptors,
                connections_count=connections_count,
                response_time_ms=response_time_ms,
                error_rate=error_rate,
                message_count=message_count,
                uptime_seconds=uptime_seconds
            )
            
            # Сохранение в историю
            self._store_metrics(bot_id, metrics)
            
            return metrics
            
        except psutil.NoSuchProcess:
            self.logger.warning(f"Process for bot {bot_id} no longer exists")
            return None
        except Exception as e:
            self.logger.error(f"Error collecting metrics for bot {bot_id}: {e}")
            return None
    
    async def health_check(self, bot_id: str) -> Optional[HealthCheckResult]:
        """Выполнение health check для бота"""
        try:
            if bot_id not in self.monitored_bots:
                return None
            
            bot_process = self.monitored_bots[bot_id]
            
            # Сбор метрик
            metrics = await self.collect_metrics(bot_id)
            if not metrics:
                # Процесс недоступен
                result = HealthCheckResult(
                    bot_id=bot_id,
                    timestamp=time.time(),
                    status=HealthStatus.FAILED,
                    metrics=ProcessMetrics(bot_id=bot_id, timestamp=time.time())
                )
                result.add_alert(AlertLevel.CRITICAL, "Process not responding or not found")
                return result
            
            # Инициализация результата
            result = HealthCheckResult(
                bot_id=bot_id,
                timestamp=time.time(),
                status=HealthStatus.HEALTHY,
                metrics=metrics
            )
            
            # Проверка по порогам
            alert_level = self._check_all_thresholds(metrics, result)
            
            # Определение общего статуса
            if alert_level == AlertLevel.CRITICAL:
                result.status = HealthStatus.CRITICAL
            elif alert_level == AlertLevel.ERROR:
                result.status = HealthStatus.FAILED
            elif alert_level == AlertLevel.WARNING:
                result.status = HealthStatus.WARNING
            else:
                result.status = HealthStatus.HEALTHY
            
            # Дополнительные проверки
            await self._additional_health_checks(bot_process, result)
            
            # Генерация рекомендаций
            self._generate_recommendations(result)
            
            # Сохранение результата
            self.last_health_checks[bot_id] = result
            
            # Отправка алертов если нужно
            if result.alerts:
                await self._send_alerts(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error during health check for bot {bot_id}: {e}")
            return None
    
    def _check_all_thresholds(self, metrics: ProcessMetrics, result: HealthCheckResult) -> Optional[AlertLevel]:
        """Проверка всех метрик против порогов"""
        max_alert_level = None
        
        # CPU check
        cpu_alert = self.threshold_manager.check_threshold('cpu', metrics.cpu_percent)
        if cpu_alert:
            result.add_alert(cpu_alert, f"High CPU usage: {metrics.cpu_percent:.1f}%", 'cpu_percent')
            max_alert_level = self._max_alert_level(max_alert_level, cpu_alert)
        
        # Memory checks
        memory_mb_alert = self.threshold_manager.check_threshold('memory', metrics.memory_usage_mb)
        if memory_mb_alert:
            result.add_alert(memory_mb_alert, f"High memory usage: {metrics.memory_usage_mb:.1f}MB", 'memory_usage_mb')
            max_alert_level = self._max_alert_level(max_alert_level, memory_mb_alert)
        
        memory_percent_alert = self.threshold_manager.check_threshold('memory', metrics.memory_percent)
        if memory_percent_alert:
            result.add_alert(memory_percent_alert, f"High memory percentage: {metrics.memory_percent:.1f}%", 'memory_percent')
            max_alert_level = self._max_alert_level(max_alert_level, memory_percent_alert)
        
        # Response time check
        response_alert = self.threshold_manager.check_threshold('response_time', metrics.response_time_ms)
        if response_alert:
            result.add_alert(response_alert, f"High response time: {metrics.response_time_ms:.1f}ms", 'response_time_ms')
            max_alert_level = self._max_alert_level(max_alert_level, response_alert)
        
        # Error rate check
        error_alert = self.threshold_manager.check_threshold('error_rate', metrics.error_rate)
        if error_alert:
            result.add_alert(error_alert, f"High error rate: {metrics.error_rate:.1f}%", 'error_rate')
            max_alert_level = self._max_alert_level(max_alert_level, error_alert)
        
        # Connections check
        conn_alert = self.threshold_manager.check_threshold('connections', metrics.connections_count)
        if conn_alert:
            result.add_alert(conn_alert, f"High connection count: {metrics.connections_count}", 'connections_count')
            max_alert_level = self._max_alert_level(max_alert_level, conn_alert)
        
        # File descriptors check
        fd_alert = self.threshold_manager.check_threshold('fd', metrics.file_descriptors)
        if fd_alert:
            result.add_alert(fd_alert, f"High file descriptor count: {metrics.file_descriptors}", 'file_descriptors')
            max_alert_level = self._max_alert_level(max_alert_level, fd_alert)
        
        return max_alert_level
    
    def _max_alert_level(self, current: Optional[AlertLevel], new: AlertLevel) -> AlertLevel:
        """Определение максимального уровня алерта"""
        if not current:
            return new
        
        levels = {AlertLevel.INFO: 1, AlertLevel.WARNING: 2, AlertLevel.ERROR: 3, AlertLevel.CRITICAL: 4}
        return current if levels[current] >= levels[new] else new
    
    async def _additional_health_checks(self, bot_process, result: HealthCheckResult):
        """Дополнительные проверки здоровья"""
        try:
            # Проверка времени работы
            min_uptime = self.threshold_manager.get_threshold('uptime_min', 'healthy')
            if min_uptime and result.metrics.uptime_seconds < min_uptime:
                result.add_alert(AlertLevel.INFO, f"Bot recently started (uptime: {result.metrics.uptime_seconds:.0f}s)")
            
            # TODO: Дополнительные application-specific checks через IPC
            # - Проверка подключения к Telegram
            # - Проверка database connectivity
            # - Проверка response latency
            
        except Exception as e:
            self.logger.error(f"Error in additional health checks for {result.bot_id}: {e}")
    
    def _generate_recommendations(self, result: HealthCheckResult):
        """Генерация рекомендаций по оптимизации"""
        if result.metrics.memory_usage_mb > 400:
            result.add_recommendation("Consider restarting the bot to free memory")
        
        if result.metrics.cpu_percent > 80:
            result.add_recommendation("High CPU usage detected - check for infinite loops or heavy operations")
        
        if result.metrics.connections_count > 8:
            result.add_recommendation("High connection count - review connection pooling settings")
        
        if result.metrics.error_rate > 5:
            result.add_recommendation("High error rate - check logs for recurring issues")
    
    def _store_metrics(self, bot_id: str, metrics: ProcessMetrics):
        """Сохранение метрик в историю"""
        if bot_id not in self.metrics_history:
            self.metrics_history[bot_id] = []
        
        history = self.metrics_history[bot_id]
        history.append(metrics)
        
        # Ограничение размера истории
        if len(history) > self.max_history_entries:
            history.pop(0)
    
    async def _send_alerts(self, result: HealthCheckResult):
        """Отправка алертов"""
        for handler in self.alert_handlers:
            try:
                await handler(result)
            except Exception as e:
                self.logger.error(f"Error sending alert: {e}")
    
    async def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        while self.is_monitoring:
            try:
                # Health check всех зарегистрированных ботов
                for bot_id in list(self.monitored_bots.keys()):
                    try:
                        await self.health_check(bot_id)
                    except Exception as e:
                        self.logger.error(f"Error health checking bot {bot_id}: {e}")
                
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _metrics_cleanup_loop(self):
        """Цикл очистки старых метрик"""
        while self.is_monitoring:
            try:
                current_time = time.time()
                max_age = 86400  # 24 часа
                
                for bot_id, history in self.metrics_history.items():
                    # Удаление старых записей
                    cutoff_time = current_time - max_age
                    self.metrics_history[bot_id] = [
                        metrics for metrics in history 
                        if metrics.timestamp > cutoff_time
                    ]
                
                await asyncio.sleep(3600)  # Очистка каждый час
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in metrics cleanup: {e}")
                await asyncio.sleep(3600)
    
    async def _performance_analysis_loop(self):
        """Цикл анализа производительности"""
        while self.is_monitoring:
            try:
                # TODO: Анализ трендов производительности
                # - Определение baseline performance
                # - Детекция деградации performance
                # - Предсказание потенциальных проблем
                
                await asyncio.sleep(300)  # Анализ каждые 5 минут
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in performance analysis: {e}")
                await asyncio.sleep(300)
    
    def add_alert_handler(self, handler: Callable):
        """Добавление обработчика алертов"""
        self.alert_handlers.append(handler)
    
    def get_bot_status(self, bot_id: str) -> Optional[Dict]:
        """Получение статуса конкретного бота"""
        if bot_id not in self.last_health_checks:
            return None
        
        result = self.last_health_checks[bot_id]
        return {
            'bot_id': bot_id,
            'status': result.status.value,
            'last_check': result.timestamp,
            'alerts_count': len(result.alerts),
            'metrics': result.metrics.to_dict(),
            'alerts': result.alerts,
            'recommendations': result.recommendations
        }
    
    def get_system_status(self) -> Dict:
        """Получение общего статуса системы"""
        total_bots = len(self.monitored_bots)
        healthy_bots = len([
            result for result in self.last_health_checks.values()
            if result.status == HealthStatus.HEALTHY
        ])
        
        return {
            'total_bots': total_bots,
            'healthy_bots': healthy_bots,
            'monitoring_active': self.is_monitoring,
            'last_update': time.time(),
            'bots': {
                bot_id: self.get_bot_status(bot_id)
                for bot_id in self.monitored_bots.keys()
            }
        }
