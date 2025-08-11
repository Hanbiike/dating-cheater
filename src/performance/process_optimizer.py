"""
ProcessSupervisor Performance Optimizer

Optimizes ProcessSupervisor performance by reducing IPC overhead,
improving resource allocation, and enhancing process coordination.
"""

import asyncio
import time
import psutil
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json

from src.utils.logger import setup_logger


@dataclass
class ProcessPerformanceMetrics:
    """Process performance metrics tracking"""
    process_id: str
    startup_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    message_count: int = 0
    average_response_time_ms: float = 0.0
    last_health_check: float = field(default_factory=time.time)
    
    def update_metrics(self, memory_mb: float, cpu_percent: float, response_time_ms: float = None):
        """Update performance metrics"""
        self.memory_usage_mb = memory_mb
        self.cpu_usage_percent = cpu_percent
        self.last_health_check = time.time()
        
        if response_time_ms is not None:
            # Calculate rolling average
            self.message_count += 1
            if self.average_response_time_ms == 0:
                self.average_response_time_ms = response_time_ms
            else:
                # Weighted average with more weight on recent measurements
                weight = min(0.3, 1.0 / self.message_count)
                self.average_response_time_ms = (
                    (1 - weight) * self.average_response_time_ms + 
                    weight * response_time_ms
                )


@dataclass
class OptimizationSettings:
    """ProcessSupervisor optimization settings"""
    # IPC optimization
    enable_message_batching: bool = True
    batch_size: int = 10
    batch_timeout_ms: int = 5
    
    # Resource optimization
    enable_adaptive_scaling: bool = True
    resource_check_interval: int = 30  # seconds
    cpu_threshold_scale_up: float = 75.0
    cpu_threshold_scale_down: float = 25.0
    memory_threshold_mb: float = 500.0
    
    # Connection optimization
    connection_pool_size: int = 20
    connection_timeout: int = 10
    keepalive_interval: int = 60
    
    # Performance monitoring
    enable_performance_monitoring: bool = True
    metrics_collection_interval: int = 10  # seconds


class ProcessSupervisorOptimizer:
    """Optimizes ProcessSupervisor performance"""
    
    def __init__(self, settings: OptimizationSettings = None):
        self.settings = settings or OptimizationSettings()
        self.logger = setup_logger(__name__)
        
        # Performance tracking
        self.process_metrics: Dict[str, ProcessPerformanceMetrics] = {}
        self.system_metrics = {
            'total_cpu_usage': 0.0,
            'total_memory_usage_gb': 0.0,
            'ipc_message_rate': 0.0,
            'average_startup_time': 0.0
        }
        
        # Message batching
        self.message_batches: Dict[str, List[Tuple[Any, float]]] = {}
        self.batch_tasks: Dict[str, asyncio.Task] = {}
        
        # Resource monitoring
        self.monitoring_task: Optional[asyncio.Task] = None
        if self.settings.enable_performance_monitoring:
            self._start_monitoring()
    
    async def optimize_process_startup(self, process_id: str, startup_func) -> float:
        """Optimize process startup with preloading and caching"""
        start_time = time.time()
        
        try:
            # Pre-warm connection pools and caches before starting process
            await self._prewarm_resources(process_id)
            
            # Start the process
            result = await startup_func()
            
            startup_time = time.time() - start_time
            
            # Track startup metrics
            if process_id not in self.process_metrics:
                self.process_metrics[process_id] = ProcessPerformanceMetrics(process_id=process_id)
            
            self.process_metrics[process_id].startup_time = startup_time
            
            self.logger.info(f"Process {process_id} started in {startup_time:.2f}s")
            return startup_time
            
        except Exception as e:
            self.logger.error(f"Process startup optimization failed for {process_id}: {e}")
            raise
    
    async def _prewarm_resources(self, process_id: str):
        """Pre-warm resources for faster process startup"""
        # This would typically:
        # 1. Pre-initialize database connections
        # 2. Pre-load configuration
        # 3. Pre-warm caches
        # 4. Set up IPC channels
        
        self.logger.debug(f"Pre-warming resources for process {process_id}")
        
        # Simulate resource prewarming
        await asyncio.sleep(0.1)  # Simulated prewarming time
    
    async def optimize_ipc_communication(self, target_process: str, message: Any) -> Any:
        """Optimize IPC communication with batching and compression"""
        if not self.settings.enable_message_batching:
            return await self._send_direct_message(target_process, message)
        
        # Add message to batch
        current_time = time.time()
        if target_process not in self.message_batches:
            self.message_batches[target_process] = []
        
        self.message_batches[target_process].append((message, current_time))
        
        # Check if batch is ready to send
        batch = self.message_batches[target_process]
        if (len(batch) >= self.settings.batch_size or 
            current_time - batch[0][1] > self.settings.batch_timeout_ms / 1000):
            
            return await self._send_batched_messages(target_process)
        
        # Start batch timeout task if not already running
        if target_process not in self.batch_tasks:
            self.batch_tasks[target_process] = asyncio.create_task(
                self._batch_timeout_handler(target_process)
            )
        
        return None  # Message will be sent in batch
    
    async def _send_direct_message(self, target_process: str, message: Any) -> Any:
        """Send message directly without batching"""
        start_time = time.time()
        
        # Simulate IPC message sending
        # In real implementation, this would use the actual IPC mechanism
        await asyncio.sleep(0.001)  # Simulated IPC latency
        
        response_time = (time.time() - start_time) * 1000
        
        # Update metrics
        if target_process in self.process_metrics:
            self.process_metrics[target_process].update_metrics(
                memory_mb=0, cpu_percent=0, response_time_ms=response_time
            )
        
        return f"response_to_{message}"
    
    async def _send_batched_messages(self, target_process: str) -> List[Any]:
        """Send batched messages to reduce IPC overhead"""
        if target_process not in self.message_batches:
            return []
        
        batch = self.message_batches[target_process]
        if not batch:
            return []
        
        start_time = time.time()
        
        # Send batch
        messages = [msg for msg, _ in batch]
        
        # Simulate batch IPC sending (more efficient than individual messages)
        await asyncio.sleep(0.002)  # Simulated batch IPC latency
        
        # Clear batch
        self.message_batches[target_process] = []
        
        # Cancel timeout task
        if target_process in self.batch_tasks:
            self.batch_tasks[target_process].cancel()
            del self.batch_tasks[target_process]
        
        response_time = (time.time() - start_time) * 1000
        
        # Update metrics
        if target_process in self.process_metrics:
            self.process_metrics[target_process].update_metrics(
                memory_mb=0, cpu_percent=0, response_time_ms=response_time / len(messages)
            )
        
        self.logger.debug(f"Sent batch of {len(messages)} messages to {target_process} in {response_time:.2f}ms")
        
        return [f"response_to_{msg}" for msg in messages]
    
    async def _batch_timeout_handler(self, target_process: str):
        """Handle batch timeout for IPC messages"""
        await asyncio.sleep(self.settings.batch_timeout_ms / 1000)
        
        if target_process in self.message_batches and self.message_batches[target_process]:
            await self._send_batched_messages(target_process)
    
    async def optimize_resource_allocation(self) -> Dict[str, Any]:
        """Optimize resource allocation based on current usage patterns"""
        recommendations = {
            'scale_up': [],
            'scale_down': [],
            'resource_adjustments': []
        }
        
        # Analyze current resource usage
        system_cpu = psutil.cpu_percent(interval=1)
        system_memory = psutil.virtual_memory()
        
        self.system_metrics['total_cpu_usage'] = system_cpu
        self.system_metrics['total_memory_usage_gb'] = system_memory.used / (1024**3)
        
        # Check each process
        for process_id, metrics in self.process_metrics.items():
            # CPU-based scaling recommendations
            if metrics.cpu_usage_percent > self.settings.cpu_threshold_scale_up:
                recommendations['scale_up'].append({
                    'process_id': process_id,
                    'reason': f'High CPU usage: {metrics.cpu_usage_percent:.1f}%',
                    'current_cpu': metrics.cpu_usage_percent
                })
            elif metrics.cpu_usage_percent < self.settings.cpu_threshold_scale_down:
                recommendations['scale_down'].append({
                    'process_id': process_id,
                    'reason': f'Low CPU usage: {metrics.cpu_usage_percent:.1f}%',
                    'current_cpu': metrics.cpu_usage_percent
                })
            
            # Memory-based adjustments
            if metrics.memory_usage_mb > self.settings.memory_threshold_mb:
                recommendations['resource_adjustments'].append({
                    'process_id': process_id,
                    'type': 'memory',
                    'action': 'increase_memory_limit',
                    'current_memory_mb': metrics.memory_usage_mb,
                    'recommended_memory_mb': metrics.memory_usage_mb * 1.5
                })
        
        # System-level recommendations
        if system_cpu > 80:
            recommendations['resource_adjustments'].append({
                'type': 'system',
                'action': 'reduce_process_count',
                'reason': f'High system CPU usage: {system_cpu:.1f}%'
            })
        
        if system_memory.percent > 85:
            recommendations['resource_adjustments'].append({
                'type': 'system',
                'action': 'optimize_memory_usage',
                'reason': f'High system memory usage: {system_memory.percent:.1f}%'
            })
        
        return recommendations
    
    def _start_monitoring(self):
        """Start background performance monitoring"""
        async def monitoring_loop():
            while True:
                try:
                    await self._collect_performance_metrics()
                    await asyncio.sleep(self.settings.metrics_collection_interval)
                except Exception as e:
                    self.logger.error(f"Performance monitoring error: {e}")
                    await asyncio.sleep(30)  # Wait longer on error
        
        self.monitoring_task = asyncio.create_task(monitoring_loop())
    
    async def _collect_performance_metrics(self):
        """Collect performance metrics for all processes"""
        # In real implementation, this would collect actual process metrics
        # For now, simulate metric collection
        
        for process_id in self.process_metrics:
            # Simulate getting process metrics
            # In reality, you'd use psutil or process monitoring
            memory_mb = 50 + (hash(process_id) % 100)  # Simulated memory usage
            cpu_percent = 10 + (hash(process_id) % 30)  # Simulated CPU usage
            
            self.process_metrics[process_id].update_metrics(memory_mb, cpu_percent)
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'system_metrics': self.system_metrics.copy(),
            'process_metrics': {},
            'optimization_settings': {
                'message_batching_enabled': self.settings.enable_message_batching,
                'adaptive_scaling_enabled': self.settings.enable_adaptive_scaling,
                'performance_monitoring_enabled': self.settings.enable_performance_monitoring
            },
            'performance_summary': {}
        }
        
        # Process metrics
        total_startup_time = 0
        process_count = 0
        
        for process_id, metrics in self.process_metrics.items():
            report['process_metrics'][process_id] = {
                'startup_time_s': metrics.startup_time,
                'memory_usage_mb': metrics.memory_usage_mb,
                'cpu_usage_percent': metrics.cpu_usage_percent,
                'average_response_time_ms': metrics.average_response_time_ms,
                'message_count': metrics.message_count,
                'last_health_check': metrics.last_health_check
            }
            
            total_startup_time += metrics.startup_time
            process_count += 1
        
        # Performance summary
        if process_count > 0:
            report['performance_summary'] = {
                'average_startup_time_s': total_startup_time / process_count,
                'total_processes': process_count,
                'average_response_time_ms': sum(
                    m.average_response_time_ms for m in self.process_metrics.values()
                ) / process_count,
                'total_messages_processed': sum(
                    m.message_count for m in self.process_metrics.values()
                )
            }
        
        return report
    
    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get optimization recommendations based on current performance"""
        recommendations = []
        
        # Check average startup time
        if self.process_metrics:
            avg_startup = sum(m.startup_time for m in self.process_metrics.values()) / len(self.process_metrics)
            if avg_startup > 3.0:
                recommendations.append({
                    'category': 'startup',
                    'priority': 'high',
                    'title': 'Optimize Process Startup Time',
                    'description': f'Average startup time is {avg_startup:.1f}s, target is <3s',
                    'actions': [
                        'Implement resource prewarming',
                        'Optimize initialization order',
                        'Cache frequently loaded data',
                        'Use process pooling'
                    ]
                })
        
        # Check IPC performance
        if self.process_metrics:
            avg_response = sum(m.average_response_time_ms for m in self.process_metrics.values()) / len(self.process_metrics)
            if avg_response > 10:
                recommendations.append({
                    'category': 'ipc',
                    'priority': 'medium',
                    'title': 'Optimize IPC Communication',
                    'description': f'Average IPC response time is {avg_response:.1f}ms, target is <10ms',
                    'actions': [
                        'Enable message batching',
                        'Optimize message serialization',
                        'Implement connection pooling',
                        'Reduce message payload size'
                    ]
                })
        
        # System resource recommendations
        if self.system_metrics['total_cpu_usage'] > 80:
            recommendations.append({
                'category': 'resources',
                'priority': 'high',
                'title': 'High System CPU Usage',
                'description': f'System CPU usage is {self.system_metrics["total_cpu_usage"]:.1f}%, consider scaling',
                'actions': [
                    'Implement horizontal scaling',
                    'Optimize CPU-intensive operations',
                    'Consider process load balancing',
                    'Review resource allocation'
                ]
            })
        
        return recommendations
    
    async def stop(self):
        """Stop optimizer and cleanup"""
        # Cancel monitoring task
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Cancel batch tasks
        for task in self.batch_tasks.values():
            task.cancel()
        
        await asyncio.gather(*self.batch_tasks.values(), return_exceptions=True)
        
        self.logger.info("ProcessSupervisor optimizer stopped")


# Factory function
def create_process_optimizer(settings: OptimizationSettings = None) -> ProcessSupervisorOptimizer:
    """Create ProcessSupervisor optimizer with optional settings"""
    return ProcessSupervisorOptimizer(settings)
