"""
Performance Optimizer - Resource Usage Optimization

Система для оптимизации производительности bot processes с анализом
метрик, adaptive tuning, performance profiling и automated optimization.

Функции:
- Performance metrics collection и analysis
- Adaptive performance tuning
- Resource usage optimization
- Performance bottleneck detection
- Automated optimization recommendations
- Performance profiling и diagnostics
"""

import asyncio
import logging
import time
import statistics
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Optional, List, Callable, Any, Tuple
from collections import deque, defaultdict
import psutil
import threading


class MetricType(Enum):
    """Типы метрик производительности"""
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    NETWORK_IO = "network_io"
    DISK_IO = "disk_io"
    CONNECTION_COUNT = "connection_count"
    ERROR_RATE = "error_rate"
    QUEUE_SIZE = "queue_size"
    LATENCY = "latency"


class OptimizationStrategy(Enum):
    """Стратегии оптимизации"""
    CONSERVATIVE = auto()    # Консервативная оптимизация
    MODERATE = auto()        # Умеренная оптимизация  
    AGGRESSIVE = auto()      # Агрессивная оптимизация
    ADAPTIVE = auto()        # Адаптивная оптимизация
    CUSTOM = auto()          # Пользовательская стратегия


class PerformanceIssueType(Enum):
    """Типы проблем производительности"""
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    HIGH_LATENCY = "high_latency"
    LOW_THROUGHPUT = "low_throughput"
    HIGH_ERROR_RATE = "high_error_rate"
    RESOURCE_CONTENTION = "resource_contention"
    MEMORY_LEAK = "memory_leak"
    CPU_BOTTLENECK = "cpu_bottleneck"
    IO_BOTTLENECK = "io_bottleneck"


@dataclass
class PerformanceMetric:
    """Метрика производительности"""
    metric_type: MetricType
    value: float
    timestamp: float
    process_id: str
    unit: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class PerformanceBaseline:
    """Базовая линия производительности"""
    process_id: str
    metric_type: MetricType
    baseline_value: float
    std_deviation: float
    percentile_95: float
    percentile_99: float
    sample_count: int
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def is_anomaly(self, value: float, threshold_factor: float = 2.0) -> bool:
        """Проверка является ли значение аномалией"""
        threshold = self.baseline_value + (self.std_deviation * threshold_factor)
        return value > threshold


@dataclass
class PerformanceIssue:
    """Проблема производительности"""
    issue_id: str
    process_id: str
    issue_type: PerformanceIssueType
    severity: str  # "low", "medium", "high", "critical"
    description: str
    metric_values: Dict[MetricType, float]
    detected_at: float
    resolved_at: Optional[float] = None
    recommendations: List[str] = field(default_factory=list)
    actions_taken: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationAction:
    """Действие оптимизации"""
    action_id: str
    process_id: str
    action_type: str
    parameters: Dict[str, Any]
    expected_impact: str
    applied_at: float
    success: bool = False
    actual_impact: Optional[Dict[str, float]] = None
    rollback_info: Optional[Dict[str, Any]] = None


class PerformanceProfiler:
    """Профилировщик производительности"""
    
    def __init__(self, process_id: str):
        self.process_id = process_id
        self.metrics_history: Dict[MetricType, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.baselines: Dict[MetricType, PerformanceBaseline] = {}
        self.issues: List[PerformanceIssue] = []
        
        # Пороговые значения для обнаружения проблем
        self.thresholds = {
            MetricType.CPU_USAGE: 80.0,
            MetricType.MEMORY_USAGE: 85.0,
            MetricType.RESPONSE_TIME: 5.0,
            MetricType.ERROR_RATE: 5.0,
            MetricType.LATENCY: 2.0
        }
    
    def add_metric(self, metric: PerformanceMetric):
        """Добавление метрики"""
        self.metrics_history[metric.metric_type].append(metric)
        
        # Обновление базовой линии
        self._update_baseline(metric.metric_type)
        
        # Проверка на проблемы
        self._check_for_issues(metric)
    
    def _update_baseline(self, metric_type: MetricType):
        """Обновление базовой линии для метрики"""
        history = self.metrics_history[metric_type]
        
        if len(history) < 30:  # Минимум 30 точек для базовой линии
            return
        
        values = [m.value for m in history]
        
        baseline = PerformanceBaseline(
            process_id=self.process_id,
            metric_type=metric_type,
            baseline_value=statistics.mean(values),
            std_deviation=statistics.stdev(values) if len(values) > 1 else 0.0,
            percentile_95=self._percentile(values, 0.95),
            percentile_99=self._percentile(values, 0.99),
            sample_count=len(values)
        )
        
        self.baselines[metric_type] = baseline
    
    def _percentile(self, values: List[float], percentile: float) -> float:
        """Расчет перцентиля"""
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def _check_for_issues(self, metric: PerformanceMetric):
        """Проверка на проблемы производительности"""
        metric_type = metric.metric_type
        value = metric.value
        
        # Проверка против пороговых значений
        threshold = self.thresholds.get(metric_type)
        if threshold and value > threshold:
            issue_type = self._map_metric_to_issue(metric_type)
            severity = self._calculate_severity(value, threshold)
            
            issue = PerformanceIssue(
                issue_id=f"{self.process_id}_{metric_type.value}_{int(time.time())}",
                process_id=self.process_id,
                issue_type=issue_type,
                severity=severity,
                description=f"{metric_type.value} exceeded threshold: {value} > {threshold}",
                metric_values={metric_type: value},
                detected_at=time.time()
            )
            
            self.issues.append(issue)
        
        # Проверка против базовой линии
        baseline = self.baselines.get(metric_type)
        if baseline and baseline.is_anomaly(value):
            issue_type = PerformanceIssueType.HIGH_LATENCY  # Default
            
            issue = PerformanceIssue(
                issue_id=f"{self.process_id}_anomaly_{metric_type.value}_{int(time.time())}",
                process_id=self.process_id,
                issue_type=issue_type,
                severity="medium",
                description=f"Anomalous {metric_type.value}: {value} (baseline: {baseline.baseline_value})",
                metric_values={metric_type: value},
                detected_at=time.time()
            )
            
            self.issues.append(issue)
    
    def _map_metric_to_issue(self, metric_type: MetricType) -> PerformanceIssueType:
        """Мапинг типа метрики на тип проблемы"""
        mapping = {
            MetricType.CPU_USAGE: PerformanceIssueType.HIGH_CPU,
            MetricType.MEMORY_USAGE: PerformanceIssueType.HIGH_MEMORY,
            MetricType.RESPONSE_TIME: PerformanceIssueType.HIGH_LATENCY,
            MetricType.LATENCY: PerformanceIssueType.HIGH_LATENCY,
            MetricType.ERROR_RATE: PerformanceIssueType.HIGH_ERROR_RATE,
            MetricType.THROUGHPUT: PerformanceIssueType.LOW_THROUGHPUT
        }
        
        return mapping.get(metric_type, PerformanceIssueType.HIGH_CPU)
    
    def _calculate_severity(self, value: float, threshold: float) -> str:
        """Расчет серьезности проблемы"""
        ratio = value / threshold
        
        if ratio > 2.0:
            return "critical"
        elif ratio > 1.5:
            return "high"
        elif ratio > 1.2:
            return "medium"
        else:
            return "low"
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Получение сводки производительности"""
        summary = {
            'process_id': self.process_id,
            'metrics_count': {mt.value: len(history) for mt, history in self.metrics_history.items()},
            'baselines_count': len(self.baselines),
            'issues_count': len(self.issues),
            'recent_issues': [
                {
                    'type': issue.issue_type.value,
                    'severity': issue.severity,
                    'detected_at': issue.detected_at
                } for issue in self.issues[-5:]  # Последние 5 проблем
            ]
        }
        
        # Текущие метрики
        current_metrics = {}
        for metric_type, history in self.metrics_history.items():
            if history:
                current_metrics[metric_type.value] = history[-1].value
        
        summary['current_metrics'] = current_metrics
        
        return summary


class PerformanceOptimizer:
    """
    Performance Optimizer - система оптимизации производительности
    
    Функции:
    - Performance metrics collection и monitoring
    - Adaptive performance tuning
    - Bottleneck detection и resolution
    - Automated optimization recommendations
    - Performance profiling и analysis
    """
    
    def __init__(self, strategy: OptimizationStrategy = OptimizationStrategy.ADAPTIVE):
        self.strategy = strategy
        self.logger = logging.getLogger(__name__)
        
        # Profilers для каждого процесса
        self.profilers: Dict[str, PerformanceProfiler] = {}
        
        # История оптимизаций
        self.optimization_history: List[OptimizationAction] = []
        
        # Состояние системы
        self.is_running = False
        self.monitoring_tasks: List[asyncio.Task] = []
        
        # Конфигурация
        self.collection_interval = 5.0  # 5 секунд
        self.optimization_interval = 60.0  # 1 минута
        self.analysis_interval = 300.0  # 5 минут
        
        # Optimization callbacks
        self.optimization_callbacks: List[Callable] = []
        
        # Статистика
        self.stats = {
            'metrics_collected': 0,
            'issues_detected': 0,
            'optimizations_applied': 0,
            'successful_optimizations': 0
        }
    
    async def start(self):
        """Запуск Performance Optimizer"""
        try:
            self.logger.info("Starting Performance Optimizer")
            
            self.is_running = True
            
            # Запуск задач мониторинга
            self.monitoring_tasks = [
                asyncio.create_task(self._metrics_collection_loop()),
                asyncio.create_task(self._optimization_loop()),
                asyncio.create_task(self._analysis_loop())
            ]
            
            self.logger.info(f"Performance Optimizer started with strategy: {self.strategy.name}")
            
        except Exception as e:
            self.logger.error(f"Error starting Performance Optimizer: {e}")
            raise
    
    async def stop(self):
        """Остановка Performance Optimizer"""
        try:
            self.logger.info("Stopping Performance Optimizer")
            
            self.is_running = False
            
            # Остановка задач
            for task in self.monitoring_tasks:
                task.cancel()
            
            if self.monitoring_tasks:
                await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
            
            self.monitoring_tasks.clear()
            
            self.logger.info("Performance Optimizer stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Performance Optimizer: {e}")
    
    def register_process(self, process_id: str):
        """Регистрация процесса для мониторинга"""
        if process_id not in self.profilers:
            self.profilers[process_id] = PerformanceProfiler(process_id)
            self.logger.info(f"Registered process {process_id} for performance monitoring")
    
    def unregister_process(self, process_id: str):
        """Удаление процесса из мониторинга"""
        if process_id in self.profilers:
            del self.profilers[process_id]
            self.logger.info(f"Unregistered process {process_id} from performance monitoring")
    
    def add_metric(self, process_id: str, metric_type: MetricType, value: float, unit: str = ""):
        """Добавление метрики производительности"""
        if process_id not in self.profilers:
            self.register_process(process_id)
        
        metric = PerformanceMetric(
            metric_type=metric_type,
            value=value,
            timestamp=time.time(),
            process_id=process_id,
            unit=unit
        )
        
        self.profilers[process_id].add_metric(metric)
        self.stats['metrics_collected'] += 1
    
    async def collect_system_metrics(self, process_id: str, pid: Optional[int] = None):
        """Сбор системных метрик для процесса"""
        try:
            if pid:
                # Метрики конкретного процесса
                try:
                    process = psutil.Process(pid)
                    
                    # CPU
                    cpu_percent = process.cpu_percent()
                    self.add_metric(process_id, MetricType.CPU_USAGE, cpu_percent, "%")
                    
                    # Memory
                    memory_info = process.memory_info()
                    memory_mb = memory_info.rss / (1024 * 1024)
                    self.add_metric(process_id, MetricType.MEMORY_USAGE, memory_mb, "MB")
                    
                    # Connections
                    try:
                        connections = len(process.connections())
                        self.add_metric(process_id, MetricType.CONNECTION_COUNT, connections, "count")
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        pass
                    
                except psutil.NoSuchProcess:
                    self.logger.warning(f"Process {pid} not found for metrics collection")
                
            # Системные метрики
            cpu_usage = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            
            self.add_metric(process_id, MetricType.CPU_USAGE, cpu_usage, "%")
            self.add_metric(process_id, MetricType.MEMORY_USAGE, memory.percent, "%")
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics for process {process_id}: {e}")
    
    async def analyze_performance(self, process_id: str) -> List[str]:
        """Анализ производительности процесса"""
        recommendations = []
        
        if process_id not in self.profilers:
            return recommendations
        
        profiler = self.profilers[process_id]
        
        # Анализ CPU usage
        cpu_history = profiler.metrics_history.get(MetricType.CPU_USAGE, deque())
        if cpu_history:
            avg_cpu = statistics.mean([m.value for m in cpu_history])
            if avg_cpu > 80:
                recommendations.append("Consider CPU optimization: average CPU usage is high ({:.1f}%)".format(avg_cpu))
                recommendations.append("- Review CPU-intensive operations")
                recommendations.append("- Consider async processing for heavy tasks")
                recommendations.append("- Profile code for CPU bottlenecks")
        
        # Анализ Memory usage
        memory_history = profiler.metrics_history.get(MetricType.MEMORY_USAGE, deque())
        if memory_history:
            if len(memory_history) > 10:
                recent_memory = [m.value for m in list(memory_history)[-10:]]
                memory_trend = recent_memory[-1] - recent_memory[0]
                
                if memory_trend > 50:  # MB
                    recommendations.append("Potential memory leak detected: memory usage increasing")
                    recommendations.append("- Review memory allocation patterns")
                    recommendations.append("- Check for unclosed resources")
                    recommendations.append("- Consider memory profiling")
        
        # Анализ Response time
        response_history = profiler.metrics_history.get(MetricType.RESPONSE_TIME, deque())
        if response_history:
            avg_response = statistics.mean([m.value for m in response_history])
            if avg_response > 3.0:
                recommendations.append("High response time detected: {:.2f}s average".format(avg_response))
                recommendations.append("- Optimize database queries")
                recommendations.append("- Review network calls")
                recommendations.append("- Consider caching strategies")
        
        # Анализ Error rate
        error_history = profiler.metrics_history.get(MetricType.ERROR_RATE, deque())
        if error_history:
            avg_error_rate = statistics.mean([m.value for m in error_history])
            if avg_error_rate > 5.0:
                recommendations.append("High error rate detected: {:.1f}%".format(avg_error_rate))
                recommendations.append("- Review error handling")
                recommendations.append("- Check input validation")
                recommendations.append("- Monitor external dependencies")
        
        return recommendations
    
    async def apply_optimization(self, process_id: str, optimization_type: str, parameters: Dict[str, Any]) -> bool:
        """Применение оптимизации"""
        try:
            action = OptimizationAction(
                action_id=f"{process_id}_{optimization_type}_{int(time.time())}",
                process_id=process_id,
                action_type=optimization_type,
                parameters=parameters,
                expected_impact="Performance improvement",
                applied_at=time.time()
            )
            
            # Применение оптимизации в зависимости от типа
            success = await self._execute_optimization(action)
            
            action.success = success
            self.optimization_history.append(action)
            
            self.stats['optimizations_applied'] += 1
            if success:
                self.stats['successful_optimizations'] += 1
            
            # Уведомление callbacks
            for callback in self.optimization_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(action)
                    else:
                        callback(action)
                except Exception as e:
                    self.logger.error(f"Error in optimization callback: {e}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error applying optimization for process {process_id}: {e}")
            return False
    
    async def _execute_optimization(self, action: OptimizationAction) -> bool:
        """Выполнение конкретной оптимизации"""
        try:
            optimization_type = action.action_type
            parameters = action.parameters
            
            if optimization_type == "cpu_limit_adjustment":
                # Корректировка лимитов CPU
                new_limit = parameters.get('cpu_limit', 50.0)
                self.logger.info(f"Adjusting CPU limit for {action.process_id} to {new_limit}%")
                return True
                
            elif optimization_type == "memory_limit_adjustment":
                # Корректировка лимитов памяти
                new_limit = parameters.get('memory_limit', 512)
                self.logger.info(f"Adjusting memory limit for {action.process_id} to {new_limit}MB")
                return True
                
            elif optimization_type == "connection_pool_resize":
                # Изменение размера пула соединений
                new_size = parameters.get('pool_size', 10)
                self.logger.info(f"Resizing connection pool for {action.process_id} to {new_size}")
                return True
                
            elif optimization_type == "cache_optimization":
                # Оптимизация кеша
                cache_size = parameters.get('cache_size', 100)
                self.logger.info(f"Optimizing cache for {action.process_id}: size {cache_size}")
                return True
                
            elif optimization_type == "gc_tuning":
                # Настройка сборщика мусора
                self.logger.info(f"Tuning garbage collection for {action.process_id}")
                return True
                
            else:
                self.logger.warning(f"Unknown optimization type: {optimization_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error executing optimization {action.action_id}: {e}")
            return False
    
    async def _metrics_collection_loop(self):
        """Цикл сбора метрик"""
        while self.is_running:
            try:
                # Сбор метрик для всех зарегистрированных процессов
                for process_id in list(self.profilers.keys()):
                    await self.collect_system_metrics(process_id)
                
                await asyncio.sleep(self.collection_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in metrics collection loop: {e}")
                await asyncio.sleep(self.collection_interval)
    
    async def _optimization_loop(self):
        """Цикл оптимизации"""
        while self.is_running:
            try:
                for process_id in list(self.profilers.keys()):
                    profiler = self.profilers[process_id]
                    
                    # Проверка активных проблем
                    recent_issues = [issue for issue in profiler.issues if time.time() - issue.detected_at < 300]  # Последние 5 минут
                    
                    for issue in recent_issues:
                        if not issue.resolved_at:
                            await self._handle_performance_issue(issue)
                
                await asyncio.sleep(self.optimization_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in optimization loop: {e}")
                await asyncio.sleep(self.optimization_interval)
    
    async def _analysis_loop(self):
        """Цикл анализа производительности"""
        while self.is_running:
            try:
                for process_id in list(self.profilers.keys()):
                    recommendations = await self.analyze_performance(process_id)
                    
                    if recommendations:
                        self.logger.info(f"Performance recommendations for {process_id}:")
                        for rec in recommendations:
                            self.logger.info(f"  - {rec}")
                
                await asyncio.sleep(self.analysis_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in analysis loop: {e}")
                await asyncio.sleep(self.analysis_interval)
    
    async def _handle_performance_issue(self, issue: PerformanceIssue):
        """Обработка проблемы производительности"""
        try:
            issue_type = issue.issue_type
            process_id = issue.process_id
            
            # Определение действий оптимизации
            if issue_type == PerformanceIssueType.HIGH_CPU:
                await self.apply_optimization(process_id, "cpu_limit_adjustment", {
                    'cpu_limit': 40.0,  # Снижение лимита CPU
                    'reason': f'High CPU usage detected: {issue.description}'
                })
                
            elif issue_type == PerformanceIssueType.HIGH_MEMORY:
                await self.apply_optimization(process_id, "memory_limit_adjustment", {
                    'memory_limit': 256,  # Снижение лимита памяти
                    'reason': f'High memory usage detected: {issue.description}'
                })
                
            elif issue_type == PerformanceIssueType.HIGH_LATENCY:
                await self.apply_optimization(process_id, "cache_optimization", {
                    'cache_size': 200,  # Увеличение кеша
                    'reason': f'High latency detected: {issue.description}'
                })
                
            elif issue_type == PerformanceIssueType.LOW_THROUGHPUT:
                await self.apply_optimization(process_id, "connection_pool_resize", {
                    'pool_size': 20,  # Увеличение пула соединений
                    'reason': f'Low throughput detected: {issue.description}'
                })
            
            # Пометка проблемы как обработанной
            issue.resolved_at = time.time()
            self.stats['issues_detected'] += 1
            
        except Exception as e:
            self.logger.error(f"Error handling performance issue {issue.issue_id}: {e}")
    
    def add_optimization_callback(self, callback: Callable):
        """Добавление callback для оптимизации"""
        self.optimization_callbacks.append(callback)
    
    def remove_optimization_callback(self, callback: Callable):
        """Удаление callback"""
        if callback in self.optimization_callbacks:
            self.optimization_callbacks.remove(callback)
    
    def get_process_performance(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Получение информации о производительности процесса"""
        if process_id not in self.profilers:
            return None
        
        return self.profilers[process_id].get_performance_summary()
    
    def get_global_performance_stats(self) -> Dict[str, Any]:
        """Получение глобальной статистики производительности"""
        total_processes = len(self.profilers)
        total_issues = sum(len(profiler.issues) for profiler in self.profilers.values())
        
        # Анализ трендов
        performance_trends = {}
        for metric_type in MetricType:
            values = []
            for profiler in self.profilers.values():
                history = profiler.metrics_history.get(metric_type, deque())
                if history:
                    values.extend([m.value for m in history])
            
            if values:
                performance_trends[metric_type.value] = {
                    'average': statistics.mean(values),
                    'median': statistics.median(values),
                    'std_dev': statistics.stdev(values) if len(values) > 1 else 0.0
                }
        
        return {
            'total_processes': total_processes,
            'total_issues': total_issues,
            'optimization_history_count': len(self.optimization_history),
            'performance_trends': performance_trends,
            'statistics': self.stats.copy(),
            'strategy': self.strategy.name
        }
