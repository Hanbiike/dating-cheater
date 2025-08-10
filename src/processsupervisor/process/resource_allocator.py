"""
Resource Allocator - Advanced Resource Allocation and Optimization

Система для управления ресурсами bot processes с оптимизацией
и dynamic allocation. Поддерживает resource limits, fair sharing,
priority-based allocation и adaptive optimization.

Функции:
- Dynamic resource allocation между bot processes
- Resource monitoring и usage tracking
- Priority-based resource scheduling
- Resource limits enforcement
- Adaptive optimization на основе metrics
- Resource conflict resolution
"""

import asyncio
import logging
import psutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Set, Tuple, Callable, Any
import threading
from statistics import mean, median
from collections import deque, defaultdict


class ResourceType(Enum):
    """Типы ресурсов"""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    DISK_IO = "disk_io"
    CONNECTIONS = "connections"
    THREADS = "threads"


class ResourcePriority(Enum):
    """Приоритеты выделения ресурсов"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class AllocationStrategy(Enum):
    """Стратегии выделения ресурсов"""
    EQUAL = "equal"           # Равное распределение
    PRIORITY = "priority"     # На основе приоритетов
    DEMAND = "demand"         # На основе потребности
    ADAPTIVE = "adaptive"     # Адаптивное распределение
    FAIR_SHARE = "fair_share" # Справедливое разделение


@dataclass
class ResourceLimits:
    """Лимиты ресурсов"""
    cpu_percent: float = 50.0        # Максимум CPU в %
    memory_mb: int = 512             # Максимум памяти в MB
    network_mbps: float = 10.0       # Максимум сети в Mbps
    disk_io_mbps: float = 50.0       # Максимум дискового IO в Mbps
    max_connections: int = 50        # Максимум соединений
    max_threads: int = 20            # Максимум потоков
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'cpu_percent': self.cpu_percent,
            'memory_mb': self.memory_mb,
            'network_mbps': self.network_mbps,
            'disk_io_mbps': self.disk_io_mbps,
            'max_connections': self.max_connections,
            'max_threads': self.max_threads
        }


@dataclass
class ResourceUsage:
    """Текущее использование ресурсов"""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    network_mbps: float = 0.0
    disk_io_mbps: float = 0.0
    connections: int = 0
    threads: int = 0
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'cpu_percent': self.cpu_percent,
            'memory_mb': self.memory_mb,
            'network_mbps': self.network_mbps,
            'disk_io_mbps': self.disk_io_mbps,
            'connections': self.connections,
            'threads': self.threads,
            'timestamp': self.timestamp
        }


@dataclass
class ResourceAllocation:
    """Выделение ресурсов для процесса"""
    process_id: str
    priority: ResourcePriority
    limits: ResourceLimits
    current_usage: ResourceUsage
    
    # Статистика
    allocated_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    violations_count: int = 0
    performance_score: float = 1.0
    
    # История использования
    usage_history: deque = field(default_factory=lambda: deque(maxlen=100))
    
    def update_usage(self, usage: ResourceUsage):
        """Обновление текущего использования"""
        self.current_usage = usage
        self.last_updated = time.time()
        self.usage_history.append(usage)
        
        # Проверка нарушений лимитов
        if self._check_violations():
            self.violations_count += 1
    
    def _check_violations(self) -> bool:
        """Проверка нарушений лимитов"""
        usage = self.current_usage
        limits = self.limits
        
        return (
            usage.cpu_percent > limits.cpu_percent or
            usage.memory_mb > limits.memory_mb or
            usage.network_mbps > limits.network_mbps or
            usage.disk_io_mbps > limits.disk_io_mbps or
            usage.connections > limits.max_connections or
            usage.threads > limits.max_threads
        )
    
    def get_utilization_stats(self) -> Dict[str, float]:
        """Получение статистики утилизации"""
        if not self.usage_history:
            return {}
        
        stats = {}
        for resource in ['cpu_percent', 'memory_mb', 'network_mbps', 'disk_io_mbps']:
            values = [getattr(usage, resource) for usage in self.usage_history]
            limit_value = getattr(self.limits, resource if resource != 'memory_mb' else 'memory_mb')
            
            if limit_value > 0:
                utilizations = [v / limit_value for v in values]
                stats[f'{resource}_avg_utilization'] = mean(utilizations)
                stats[f'{resource}_max_utilization'] = max(utilizations)
                stats[f'{resource}_median_utilization'] = median(utilizations)
        
        return stats


class ResourceMonitor:
    """Мониторинг ресурсов системы"""
    
    def __init__(self, update_interval: float = 1.0):
        self.update_interval = update_interval
        self.logger = logging.getLogger(__name__)
        
        # Состояние
        self.is_running = False
        self.monitoring_thread: Optional[threading.Thread] = None
        
        # Системные ресурсы
        self.system_resources = {
            'cpu_count': psutil.cpu_count(),
            'memory_total': psutil.virtual_memory().total / (1024 * 1024),  # MB
            'disk_io_capacity': 1000.0,  # MB/s - estimated
            'network_capacity': 100.0    # Mbps - estimated
        }
        
        # История системных метрик
        self.system_history: deque = deque(maxlen=300)  # 5 минут при интервале 1 сек
        
        # Process monitoring
        self.process_monitors: Dict[str, psutil.Process] = {}
        self.process_usage: Dict[str, ResourceUsage] = {}
        
        # Callbacks
        self.usage_callbacks: List[Callable] = []
    
    def start(self):
        """Запуск мониторинга"""
        if self.is_running:
            return
        
        self.is_running = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        self.logger.info("Resource Monitor started")
    
    def stop(self):
        """Остановка мониторинга"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5.0)
        
        self.logger.info("Resource Monitor stopped")
    
    def add_process(self, process_id: str, pid: int):
        """Добавление процесса для мониторинга"""
        try:
            process = psutil.Process(pid)
            self.process_monitors[process_id] = process
            self.process_usage[process_id] = ResourceUsage()
            
            self.logger.debug(f"Added process {process_id} (PID: {pid}) to monitoring")
            
        except psutil.NoSuchProcess:
            self.logger.error(f"Process with PID {pid} not found")
        except Exception as e:
            self.logger.error(f"Error adding process {process_id}: {e}")
    
    def remove_process(self, process_id: str):
        """Удаление процесса из мониторинга"""
        if process_id in self.process_monitors:
            del self.process_monitors[process_id]
        
        if process_id in self.process_usage:
            del self.process_usage[process_id]
        
        self.logger.debug(f"Removed process {process_id} from monitoring")
    
    def get_process_usage(self, process_id: str) -> Optional[ResourceUsage]:
        """Получение использования ресурсов процесса"""
        return self.process_usage.get(process_id)
    
    def get_system_usage(self) -> Dict[str, float]:
        """Получение использования системных ресурсов"""
        try:
            cpu_usage = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk_io = psutil.disk_io_counters()
            network_io = psutil.net_io_counters()
            
            return {
                'cpu_percent': cpu_usage,
                'memory_percent': memory.percent,
                'memory_used_mb': memory.used / (1024 * 1024),
                'memory_available_mb': memory.available / (1024 * 1024),
                'disk_read_mbps': getattr(disk_io, 'read_bytes', 0) / (1024 * 1024),
                'disk_write_mbps': getattr(disk_io, 'write_bytes', 0) / (1024 * 1024),
                'network_sent_mbps': getattr(network_io, 'bytes_sent', 0) / (1024 * 1024),
                'network_recv_mbps': getattr(network_io, 'bytes_recv', 0) / (1024 * 1024)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting system usage: {e}")
            return {}
    
    def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        last_disk_io = None
        last_network_io = None
        last_time = time.time()
        
        while self.is_running:
            try:
                current_time = time.time()
                time_delta = current_time - last_time
                
                # Системные метрики
                system_usage = self.get_system_usage()
                self.system_history.append((current_time, system_usage))
                
                # Метрики процессов
                for process_id, process in list(self.process_monitors.items()):
                    try:
                        if not process.is_running():
                            self.remove_process(process_id)
                            continue
                        
                        # CPU
                        cpu_percent = process.cpu_percent()
                        
                        # Memory
                        memory_info = process.memory_info()
                        memory_mb = memory_info.rss / (1024 * 1024)
                        
                        # IO
                        io_counters = process.io_counters()
                        
                        # Connections и threads
                        try:
                            connections = len(process.connections())
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            connections = 0
                        
                        try:
                            threads = process.num_threads()
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            threads = 0
                        
                        # Обновление usage
                        usage = ResourceUsage(
                            cpu_percent=cpu_percent,
                            memory_mb=memory_mb,
                            network_mbps=0.0,  # Пока не реализовано на уровне процесса
                            disk_io_mbps=0.0,  # Пока не реализовано на уровне процесса
                            connections=connections,
                            threads=threads,
                            timestamp=current_time
                        )
                        
                        self.process_usage[process_id] = usage
                        
                        # Уведомление callbacks
                        for callback in self.usage_callbacks:
                            try:
                                callback(process_id, usage)
                            except Exception as e:
                                self.logger.error(f"Error in usage callback: {e}")
                                
                    except psutil.NoSuchProcess:
                        self.remove_process(process_id)
                    except Exception as e:
                        self.logger.error(f"Error monitoring process {process_id}: {e}")
                
                last_time = current_time
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.update_interval)
    
    def add_usage_callback(self, callback: Callable):
        """Добавление callback для обновлений usage"""
        self.usage_callbacks.append(callback)
    
    def remove_usage_callback(self, callback: Callable):
        """Удаление callback"""
        if callback in self.usage_callbacks:
            self.usage_callbacks.remove(callback)


class ResourceAllocator:
    """
    Resource Allocator - система управления ресурсами для ProcessSupervisor
    
    Функции:
    - Dynamic resource allocation между bot processes
    - Resource monitoring и usage optimization
    - Priority-based scheduling
    - Resource limits enforcement
    - Adaptive resource reallocation
    """
    
    def __init__(self, strategy: AllocationStrategy = AllocationStrategy.ADAPTIVE):
        self.strategy = strategy
        self.logger = logging.getLogger(__name__)
        
        # Resource monitoring
        self.monitor = ResourceMonitor()
        self.monitor.add_usage_callback(self._on_usage_update)
        
        # Resource allocations
        self.allocations: Dict[str, ResourceAllocation] = {}
        
        # Global resource limits
        self.global_limits = ResourceLimits(
            cpu_percent=80.0,      # 80% от всех CPU
            memory_mb=4096,        # 4GB памяти
            network_mbps=100.0,    # 100 Mbps
            disk_io_mbps=500.0,    # 500 MB/s
            max_connections=1000,  # 1000 соединений
            max_threads=200        # 200 потоков
        )
        
        # Resource pools
        self.resource_pools: Dict[ResourceType, float] = {}
        self._initialize_resource_pools()
        
        # Optimization
        self.optimization_enabled = True
        self.optimization_interval = 60.0  # 1 минута
        self.optimization_task: Optional[asyncio.Task] = None
        
        # История реаллокаций
        self.reallocation_history: deque = deque(maxlen=1000)
        
        # Состояние
        self.is_running = False
    
    async def start(self):
        """Запуск Resource Allocator"""
        try:
            self.logger.info("Starting Resource Allocator")
            
            # Запуск мониторинга
            self.monitor.start()
            
            # Инициализация resource pools
            self._initialize_resource_pools()
            
            self.is_running = True
            
            # Запуск оптимизации
            if self.optimization_enabled:
                self.optimization_task = asyncio.create_task(self._optimization_loop())
            
            self.logger.info(f"Resource Allocator started with strategy: {self.strategy.value}")
            
        except Exception as e:
            self.logger.error(f"Error starting Resource Allocator: {e}")
            raise
    
    async def stop(self):
        """Остановка Resource Allocator"""
        try:
            self.logger.info("Stopping Resource Allocator")
            
            self.is_running = False
            
            # Остановка оптимизации
            if self.optimization_task:
                self.optimization_task.cancel()
                try:
                    await self.optimization_task
                except asyncio.CancelledError:
                    pass
            
            # Остановка мониторинга
            self.monitor.stop()
            
            self.logger.info("Resource Allocator stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Resource Allocator: {e}")
    
    async def allocate_resources(self, process_id: str, priority: ResourcePriority = ResourcePriority.NORMAL,
                               requested_limits: Optional[ResourceLimits] = None) -> ResourceAllocation:
        """Выделение ресурсов для процесса"""
        try:
            # Определение лимитов
            if requested_limits:
                limits = requested_limits
            else:
                limits = self._calculate_default_limits(priority)
            
            # Проверка доступности ресурсов
            if not self._check_resource_availability(limits):
                # Попытка оптимизации существующих выделений
                await self._optimize_allocations()
                
                if not self._check_resource_availability(limits):
                    # Снижение лимитов
                    limits = self._reduce_limits(limits, 0.7)  # 70% от запрашиваемых
            
            # Создание allocation
            allocation = ResourceAllocation(
                process_id=process_id,
                priority=priority,
                limits=limits,
                current_usage=ResourceUsage()
            )
            
            # Резервирование ресурсов
            self._reserve_resources(limits)
            
            # Сохранение allocation
            self.allocations[process_id] = allocation
            
            self.logger.info(f"Allocated resources for process {process_id}: {limits.to_dict()}")
            
            return allocation
            
        except Exception as e:
            self.logger.error(f"Error allocating resources for process {process_id}: {e}")
            raise
    
    async def deallocate_resources(self, process_id: str):
        """Освобождение ресурсов процесса"""
        try:
            if process_id not in self.allocations:
                return
            
            allocation = self.allocations[process_id]
            
            # Освобождение ресурсов
            self._release_resources(allocation.limits)
            
            # Удаление allocation
            del self.allocations[process_id]
            
            # Удаление из мониторинга
            self.monitor.remove_process(process_id)
            
            self.logger.info(f"Deallocated resources for process {process_id}")
            
        except Exception as e:
            self.logger.error(f"Error deallocating resources for process {process_id}: {e}")
    
    async def update_allocation(self, process_id: str, new_limits: ResourceLimits) -> bool:
        """Обновление выделения ресурсов"""
        try:
            if process_id not in self.allocations:
                return False
            
            allocation = self.allocations[process_id]
            old_limits = allocation.limits
            
            # Проверка доступности новых ресурсов
            temp_limits = ResourceLimits(
                cpu_percent=max(0, new_limits.cpu_percent - old_limits.cpu_percent),
                memory_mb=max(0, new_limits.memory_mb - old_limits.memory_mb),
                network_mbps=max(0, new_limits.network_mbps - old_limits.network_mbps),
                disk_io_mbps=max(0, new_limits.disk_io_mbps - old_limits.disk_io_mbps),
                max_connections=max(0, new_limits.max_connections - old_limits.max_connections),
                max_threads=max(0, new_limits.max_threads - old_limits.max_threads)
            )
            
            if not self._check_resource_availability(temp_limits):
                return False
            
            # Обновление резервирования
            self._release_resources(old_limits)
            self._reserve_resources(new_limits)
            
            # Обновление allocation
            allocation.limits = new_limits
            allocation.last_updated = time.time()
            
            # История изменений
            self.reallocation_history.append({
                'process_id': process_id,
                'timestamp': time.time(),
                'old_limits': old_limits.to_dict(),
                'new_limits': new_limits.to_dict(),
                'reason': 'manual_update'
            })
            
            self.logger.info(f"Updated allocation for process {process_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating allocation for process {process_id}: {e}")
            return False
    
    def add_process_monitoring(self, process_id: str, pid: int):
        """Добавление процесса в мониторинг"""
        self.monitor.add_process(process_id, pid)
    
    def get_allocation(self, process_id: str) -> Optional[ResourceAllocation]:
        """Получение allocation для процесса"""
        return self.allocations.get(process_id)
    
    def get_resource_utilization(self) -> Dict[str, float]:
        """Получение утилизации ресурсов"""
        total_allocated = {
            'cpu_percent': 0.0,
            'memory_mb': 0.0,
            'network_mbps': 0.0,
            'disk_io_mbps': 0.0,
            'connections': 0,
            'threads': 0
        }
        
        total_used = {
            'cpu_percent': 0.0,
            'memory_mb': 0.0,
            'network_mbps': 0.0,
            'disk_io_mbps': 0.0,
            'connections': 0,
            'threads': 0
        }
        
        for allocation in self.allocations.values():
            # Выделенные ресурсы
            total_allocated['cpu_percent'] += allocation.limits.cpu_percent
            total_allocated['memory_mb'] += allocation.limits.memory_mb
            total_allocated['network_mbps'] += allocation.limits.network_mbps
            total_allocated['disk_io_mbps'] += allocation.limits.disk_io_mbps
            total_allocated['connections'] += allocation.limits.max_connections
            total_allocated['threads'] += allocation.limits.max_threads
            
            # Используемые ресурсы
            usage = allocation.current_usage
            total_used['cpu_percent'] += usage.cpu_percent
            total_used['memory_mb'] += usage.memory_mb
            total_used['network_mbps'] += usage.network_mbps
            total_used['disk_io_mbps'] += usage.disk_io_mbps
            total_used['connections'] += usage.connections
            total_used['threads'] += usage.threads
        
        # Расчет утилизации
        utilization = {}
        for resource in total_allocated:
            allocated = total_allocated[resource]
            used = total_used[resource]
            
            if allocated > 0:
                utilization[f'{resource}_allocation_utilization'] = used / allocated
            else:
                utilization[f'{resource}_allocation_utilization'] = 0.0
            
            # Утилизация от глобальных лимитов
            global_limit = getattr(self.global_limits, resource if resource != 'connections' and resource != 'threads' else f'max_{resource.rstrip("s")}', 0)
            if global_limit > 0:
                utilization[f'{resource}_global_utilization'] = allocated / global_limit
        
        return utilization
    
    def _initialize_resource_pools(self):
        """Инициализация пулов ресурсов"""
        system_resources = self.monitor.system_resources
        
        self.resource_pools = {
            ResourceType.CPU: min(self.global_limits.cpu_percent, 90.0),
            ResourceType.MEMORY: min(self.global_limits.memory_mb, system_resources['memory_total'] * 0.8),
            ResourceType.NETWORK: self.global_limits.network_mbps,
            ResourceType.DISK_IO: self.global_limits.disk_io_mbps,
            ResourceType.CONNECTIONS: self.global_limits.max_connections,
            ResourceType.THREADS: self.global_limits.max_threads
        }
    
    def _calculate_default_limits(self, priority: ResourcePriority) -> ResourceLimits:
        """Расчет лимитов по умолчанию"""
        base_multiplier = {
            ResourcePriority.LOW: 0.5,
            ResourcePriority.NORMAL: 1.0,
            ResourcePriority.HIGH: 1.5,
            ResourcePriority.CRITICAL: 2.0
        }.get(priority, 1.0)
        
        return ResourceLimits(
            cpu_percent=20.0 * base_multiplier,
            memory_mb=int(256 * base_multiplier),
            network_mbps=5.0 * base_multiplier,
            disk_io_mbps=25.0 * base_multiplier,
            max_connections=int(25 * base_multiplier),
            max_threads=int(10 * base_multiplier)
        )
    
    def _check_resource_availability(self, limits: ResourceLimits) -> bool:
        """Проверка доступности ресурсов"""
        current_allocated = {
            'cpu_percent': sum(a.limits.cpu_percent for a in self.allocations.values()),
            'memory_mb': sum(a.limits.memory_mb for a in self.allocations.values()),
            'network_mbps': sum(a.limits.network_mbps for a in self.allocations.values()),
            'disk_io_mbps': sum(a.limits.disk_io_mbps for a in self.allocations.values()),
            'max_connections': sum(a.limits.max_connections for a in self.allocations.values()),
            'max_threads': sum(a.limits.max_threads for a in self.allocations.values())
        }
        
        return (
            current_allocated['cpu_percent'] + limits.cpu_percent <= self.global_limits.cpu_percent and
            current_allocated['memory_mb'] + limits.memory_mb <= self.global_limits.memory_mb and
            current_allocated['network_mbps'] + limits.network_mbps <= self.global_limits.network_mbps and
            current_allocated['disk_io_mbps'] + limits.disk_io_mbps <= self.global_limits.disk_io_mbps and
            current_allocated['max_connections'] + limits.max_connections <= self.global_limits.max_connections and
            current_allocated['max_threads'] + limits.max_threads <= self.global_limits.max_threads
        )
    
    def _reserve_resources(self, limits: ResourceLimits):
        """Резервирование ресурсов"""
        # В текущей реализации просто логгируем
        self.logger.debug(f"Reserved resources: {limits.to_dict()}")
    
    def _release_resources(self, limits: ResourceLimits):
        """Освобождение ресурсов"""
        # В текущей реализации просто логгируем
        self.logger.debug(f"Released resources: {limits.to_dict()}")
    
    def _reduce_limits(self, limits: ResourceLimits, factor: float) -> ResourceLimits:
        """Снижение лимитов на указанный коэффициент"""
        return ResourceLimits(
            cpu_percent=limits.cpu_percent * factor,
            memory_mb=int(limits.memory_mb * factor),
            network_mbps=limits.network_mbps * factor,
            disk_io_mbps=limits.disk_io_mbps * factor,
            max_connections=int(limits.max_connections * factor),
            max_threads=int(limits.max_threads * factor)
        )
    
    def _on_usage_update(self, process_id: str, usage: ResourceUsage):
        """Callback для обновления usage"""
        if process_id in self.allocations:
            allocation = self.allocations[process_id]
            allocation.update_usage(usage)
    
    async def _optimization_loop(self):
        """Цикл оптимизации ресурсов"""
        while self.is_running:
            try:
                await asyncio.sleep(self.optimization_interval)
                
                if self.strategy == AllocationStrategy.ADAPTIVE:
                    await self._adaptive_optimization()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in optimization loop: {e}")
    
    async def _optimize_allocations(self):
        """Оптимизация существующих выделений"""
        try:
            if self.strategy == AllocationStrategy.ADAPTIVE:
                await self._adaptive_optimization()
            elif self.strategy == AllocationStrategy.FAIR_SHARE:
                await self._fair_share_optimization()
            elif self.strategy == AllocationStrategy.PRIORITY:
                await self._priority_optimization()
                
        except Exception as e:
            self.logger.error(f"Error optimizing allocations: {e}")
    
    async def _adaptive_optimization(self):
        """Адаптивная оптимизация ресурсов"""
        try:
            reallocation_count = 0
            
            for process_id, allocation in self.allocations.items():
                if not allocation.usage_history:
                    continue
                
                # Анализ использования
                stats = allocation.get_utilization_stats()
                
                # Определение необходимости реаллокации
                needs_adjustment = False
                new_limits = ResourceLimits(**allocation.limits.to_dict())
                
                # CPU оптимизация
                cpu_avg_util = stats.get('cpu_percent_avg_utilization', 0)
                if cpu_avg_util < 0.3:  # Недоиспользование
                    new_limits.cpu_percent *= 0.8
                    needs_adjustment = True
                elif cpu_avg_util > 0.8:  # Перегрузка
                    new_limits.cpu_percent *= 1.2
                    needs_adjustment = True
                
                # Memory оптимизация
                memory_avg_util = stats.get('memory_mb_avg_utilization', 0)
                if memory_avg_util < 0.3:
                    new_limits.memory_mb = int(new_limits.memory_mb * 0.8)
                    needs_adjustment = True
                elif memory_avg_util > 0.8:
                    new_limits.memory_mb = int(new_limits.memory_mb * 1.2)
                    needs_adjustment = True
                
                # Применение изменений
                if needs_adjustment:
                    success = await self.update_allocation(process_id, new_limits)
                    if success:
                        reallocation_count += 1
                        
                        # Запись в историю
                        self.reallocation_history.append({
                            'process_id': process_id,
                            'timestamp': time.time(),
                            'old_limits': allocation.limits.to_dict(),
                            'new_limits': new_limits.to_dict(),
                            'reason': 'adaptive_optimization',
                            'stats': stats
                        })
            
            if reallocation_count > 0:
                self.logger.info(f"Adaptive optimization: reallocated {reallocation_count} processes")
                
        except Exception as e:
            self.logger.error(f"Error in adaptive optimization: {e}")
    
    async def _fair_share_optimization(self):
        """Оптимизация справедливого распределения"""
        # Простая реализация - равное распределение между процессами одного приоритета
        priority_groups = defaultdict(list)
        
        for process_id, allocation in self.allocations.items():
            priority_groups[allocation.priority].append((process_id, allocation))
        
        for priority, processes in priority_groups.items():
            if len(processes) <= 1:
                continue
            
            # Расчет средних лимитов для группы
            total_limits = ResourceLimits()
            for _, allocation in processes:
                total_limits.cpu_percent += allocation.limits.cpu_percent
                total_limits.memory_mb += allocation.limits.memory_mb
                total_limits.network_mbps += allocation.limits.network_mbps
                total_limits.disk_io_mbps += allocation.limits.disk_io_mbps
                total_limits.max_connections += allocation.limits.max_connections
                total_limits.max_threads += allocation.limits.max_threads
            
            # Равное распределение
            count = len(processes)
            fair_limits = ResourceLimits(
                cpu_percent=total_limits.cpu_percent / count,
                memory_mb=int(total_limits.memory_mb / count),
                network_mbps=total_limits.network_mbps / count,
                disk_io_mbps=total_limits.disk_io_mbps / count,
                max_connections=int(total_limits.max_connections / count),
                max_threads=int(total_limits.max_threads / count)
            )
            
            # Применение к каждому процессу
            for process_id, _ in processes:
                await self.update_allocation(process_id, fair_limits)
    
    async def _priority_optimization(self):
        """Оптимизация на основе приоритетов"""
        # Сортировка по приоритетам
        sorted_allocations = sorted(
            self.allocations.items(),
            key=lambda x: x[1].priority.value,
            reverse=True
        )
        
        # Перераспределение ресурсов в пользу высокоприоритетных процессов
        for i, (process_id, allocation) in enumerate(sorted_allocations):
            if allocation.priority == ResourcePriority.CRITICAL:
                # Увеличение лимитов для критических процессов
                new_limits = ResourceLimits(
                    cpu_percent=min(allocation.limits.cpu_percent * 1.5, 80.0),
                    memory_mb=min(int(allocation.limits.memory_mb * 1.5), 2048),
                    network_mbps=min(allocation.limits.network_mbps * 1.5, 50.0),
                    disk_io_mbps=min(allocation.limits.disk_io_mbps * 1.5, 200.0),
                    max_connections=min(int(allocation.limits.max_connections * 1.5), 200),
                    max_threads=min(int(allocation.limits.max_threads * 1.5), 50)
                )
                
                await self.update_allocation(process_id, new_limits)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики Resource Allocator"""
        total_processes = len(self.allocations)
        
        if total_processes == 0:
            return {
                'total_processes': 0,
                'resource_utilization': {},
                'reallocation_count': len(self.reallocation_history)
            }
        
        # Статистика по приоритетам
        priority_stats = defaultdict(int)
        for allocation in self.allocations.values():
            priority_stats[allocation.priority.value] += 1
        
        # Статистика нарушений
        total_violations = sum(allocation.violations_count for allocation in self.allocations.values())
        
        return {
            'total_processes': total_processes,
            'priority_distribution': dict(priority_stats),
            'resource_utilization': self.get_resource_utilization(),
            'total_violations': total_violations,
            'reallocation_count': len(self.reallocation_history),
            'strategy': self.strategy.value,
            'optimization_enabled': self.optimization_enabled,
            'global_limits': self.global_limits.to_dict()
        }
