"""
Performance Monitoring Dashboard

Comprehensive performance monitoring and alerting system for the
multi-bot production environment with real-time metrics and analytics.
"""

import asyncio
import time
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import deque, defaultdict
import statistics

from src.performance.analyzer import PerformanceAnalyzer
from src.performance.smart_cache import SmartCacheManager
from src.performance.process_optimizer import ProcessSupervisorOptimizer
from src.utils.logger import setup_logger


@dataclass
class PerformanceAlert:
    """Performance alert definition"""
    alert_id: str
    severity: str  # critical, warning, info
    title: str
    description: str
    metric_name: str
    threshold: float
    current_value: float
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False


@dataclass
class MetricThreshold:
    """Metric threshold configuration"""
    metric_name: str
    warning_threshold: float
    critical_threshold: float
    comparison: str = "greater"  # greater, less, equal
    enabled: bool = True


class PerformanceMonitor:
    """Comprehensive performance monitoring system"""
    
    def __init__(self):
        self.logger = setup_logger(__name__)
        
        # Components
        self.analyzer: Optional[PerformanceAnalyzer] = None
        self.cache_manager: Optional[SmartCacheManager] = None
        self.process_optimizer: Optional[ProcessSupervisorOptimizer] = None
        
        # Metrics storage
        self.metrics_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.current_metrics: Dict[str, Any] = {}
        self.performance_trends: Dict[str, List[float]] = defaultdict(list)
        
        # Alerting
        self.active_alerts: Dict[str, PerformanceAlert] = {}
        self.alert_history: deque = deque(maxlen=500)
        self.thresholds: List[MetricThreshold] = self._initialize_thresholds()
        
        # Monitoring tasks
        self.monitoring_task: Optional[asyncio.Task] = None
        self.dashboard_task: Optional[asyncio.Task] = None
        
        # Configuration
        self.monitoring_interval = 30  # seconds
        self.trend_window_minutes = 60
        self.alert_cooldown_minutes = 5
    
    def _initialize_thresholds(self) -> List[MetricThreshold]:
        """Initialize default performance thresholds"""
        return [
            # Database performance thresholds
            MetricThreshold("db_query_time_ms", 75.0, 150.0),
            MetricThreshold("db_connection_pool_usage", 0.8, 0.95),
            
            # Cache performance thresholds
            MetricThreshold("cache_hit_ratio", 0.7, 0.5, "less"),
            MetricThreshold("cache_access_time_ms", 5.0, 15.0),
            
            # System resource thresholds
            MetricThreshold("cpu_usage_percent", 75.0, 90.0),
            MetricThreshold("memory_usage_percent", 80.0, 95.0),
            MetricThreshold("disk_usage_percent", 85.0, 95.0),
            
            # Process performance thresholds
            MetricThreshold("process_startup_time_s", 3.0, 5.0),
            MetricThreshold("ipc_response_time_ms", 10.0, 25.0),
            MetricThreshold("process_memory_mb", 500.0, 1000.0)
        ]
    
    async def initialize(self, analyzer: PerformanceAnalyzer = None, 
                        cache_manager: SmartCacheManager = None,
                        process_optimizer: ProcessSupervisorOptimizer = None):
        """Initialize monitoring with optional component injection"""
        self.analyzer = analyzer or PerformanceAnalyzer()
        self.cache_manager = cache_manager
        self.process_optimizer = process_optimizer
        
        # Start monitoring
        await self.start_monitoring()
        
        self.logger.info("Performance monitoring initialized")
    
    async def start_monitoring(self):
        """Start background monitoring tasks"""
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.dashboard_task = asyncio.create_task(self._dashboard_update_loop())
        
        self.logger.info("Performance monitoring started")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while True:
            try:
                await self._collect_metrics()
                await self._analyze_trends()
                await self._check_alerts()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _dashboard_update_loop(self):
        """Update dashboard data loop"""
        while True:
            try:
                await self._update_dashboard_data()
                await asyncio.sleep(10)  # Update dashboard every 10 seconds
            except Exception as e:
                self.logger.error(f"Dashboard update error: {e}")
                await asyncio.sleep(30)
    
    async def _collect_metrics(self):
        """Collect metrics from all monitoring components"""
        timestamp = time.time()
        
        # System metrics (always available)
        try:
            if self.analyzer:
                system_results = await self.analyzer._analyze_system_resources()
                self._record_metric('cpu_usage_percent', system_results.get('cpu', {}).get('usage_percent', 0), timestamp)
                self._record_metric('memory_usage_percent', system_results.get('memory', {}).get('usage_percent', 0), timestamp)
                self._record_metric('disk_usage_percent', system_results.get('disk', {}).get('usage_percent', 0), timestamp)
                self._record_metric('memory_available_gb', system_results.get('memory', {}).get('available_gb', 0), timestamp)
        except Exception as e:
            self.logger.warning(f"System metrics collection failed: {e}")
        
        # Cache metrics
        if self.cache_manager:
            try:
                cache_stats = self.cache_manager.get_performance_stats()
                self._record_metric('cache_hit_ratio', cache_stats.get('cache_hit_ratio', 0), timestamp)
                self._record_metric('cache_access_time_ms', cache_stats.get('average_access_time_ms', 0), timestamp)
                self._record_metric('cache_operations_total', cache_stats.get('total_operations', 0), timestamp)
            except Exception as e:
                self.logger.warning(f"Cache metrics collection failed: {e}")
        
        # Process metrics
        if self.process_optimizer:
            try:
                process_report = self.process_optimizer.get_performance_report()
                summary = process_report.get('performance_summary', {})
                
                self._record_metric('process_startup_time_s', summary.get('average_startup_time_s', 0), timestamp)
                self._record_metric('ipc_response_time_ms', summary.get('average_response_time_ms', 0), timestamp)
                self._record_metric('total_processes', summary.get('total_processes', 0), timestamp)
                self._record_metric('total_messages_processed', summary.get('total_messages_processed', 0), timestamp)
            except Exception as e:
                self.logger.warning(f"Process metrics collection failed: {e}")
    
    def _record_metric(self, metric_name: str, value: float, timestamp: float):
        """Record a metric value with timestamp"""
        self.metrics_history[metric_name].append((timestamp, value))
        self.current_metrics[metric_name] = value
        
        # Update trend data
        if len(self.performance_trends[metric_name]) >= 100:  # Keep last 100 values
            self.performance_trends[metric_name].pop(0)
        self.performance_trends[metric_name].append(value)
    
    async def _analyze_trends(self):
        """Analyze performance trends"""
        current_time = time.time()
        cutoff_time = current_time - (self.trend_window_minutes * 60)
        
        for metric_name, history in self.metrics_history.items():
            # Filter recent data
            recent_data = [(t, v) for t, v in history if t > cutoff_time]
            
            if len(recent_data) < 5:  # Need at least 5 data points
                continue
            
            values = [v for _, v in recent_data]
            
            # Calculate trend metrics
            trend_data = {
                'mean': statistics.mean(values),
                'median': statistics.median(values),
                'std_dev': statistics.stdev(values) if len(values) > 1 else 0,
                'min': min(values),
                'max': max(values),
                'trend_direction': self._calculate_trend_direction(values)
            }
            
            self.current_metrics[f'{metric_name}_trend'] = trend_data
    
    def _calculate_trend_direction(self, values: List[float]) -> str:
        """Calculate trend direction (increasing, decreasing, stable)"""
        if len(values) < 3:
            return 'unknown'
        
        # Simple linear trend calculation
        recent_third = values[-len(values)//3:]
        earlier_third = values[:len(values)//3]
        
        recent_avg = statistics.mean(recent_third)
        earlier_avg = statistics.mean(earlier_third)
        
        change_percent = ((recent_avg - earlier_avg) / earlier_avg * 100) if earlier_avg != 0 else 0
        
        if abs(change_percent) < 5:  # Less than 5% change
            return 'stable'
        elif change_percent > 0:
            return 'increasing'
        else:
            return 'decreasing'
    
    async def _check_alerts(self):
        """Check metrics against thresholds and generate alerts"""
        current_time = time.time()
        
        for threshold in self.thresholds:
            if not threshold.enabled:
                continue
            
            metric_value = self.current_metrics.get(threshold.metric_name)
            if metric_value is None:
                continue
            
            # Check if alert conditions are met
            alert_triggered = False
            severity = None
            
            if threshold.comparison == "greater":
                if metric_value >= threshold.critical_threshold:
                    alert_triggered = True
                    severity = "critical"
                elif metric_value >= threshold.warning_threshold:
                    alert_triggered = True
                    severity = "warning"
            elif threshold.comparison == "less":
                if metric_value <= threshold.critical_threshold:
                    alert_triggered = True
                    severity = "critical"
                elif metric_value <= threshold.warning_threshold:
                    alert_triggered = True
                    severity = "warning"
            
            if alert_triggered:
                alert_id = f"{threshold.metric_name}_{severity}"
                
                # Check if alert already exists and is within cooldown
                existing_alert = self.active_alerts.get(alert_id)
                if existing_alert and (current_time - existing_alert.timestamp) < (self.alert_cooldown_minutes * 60):
                    continue
                
                # Create new alert
                alert = PerformanceAlert(
                    alert_id=alert_id,
                    severity=severity,
                    title=f"{threshold.metric_name.replace('_', ' ').title()} {severity.upper()}",
                    description=f"{threshold.metric_name} is {metric_value:.2f}, threshold is {threshold.warning_threshold if severity == 'warning' else threshold.critical_threshold:.2f}",
                    metric_name=threshold.metric_name,
                    threshold=threshold.warning_threshold if severity == "warning" else threshold.critical_threshold,
                    current_value=metric_value
                )
                
                self.active_alerts[alert_id] = alert
                self.alert_history.append(alert)
                
                self.logger.warning(f"Performance alert: {alert.title} - {alert.description}")
    
    async def _update_dashboard_data(self):
        """Update dashboard data structure"""
        dashboard_data = {
            'timestamp': datetime.now().isoformat(),
            'status': self._get_overall_status(),
            'metrics_summary': self._get_metrics_summary(),
            'active_alerts': [asdict(alert) for alert in self.active_alerts.values()],
            'performance_trends': self._get_trend_summary(),
            'recommendations': await self._get_optimization_recommendations()
        }
        
        # Save dashboard data to file for external access
        try:
            with open('performance_dashboard.json', 'w') as f:
                json.dump(dashboard_data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save dashboard data: {e}")
    
    def _get_overall_status(self) -> str:
        """Get overall system status"""
        if any(alert.severity == "critical" for alert in self.active_alerts.values()):
            return "critical"
        elif any(alert.severity == "warning" for alert in self.active_alerts.values()):
            return "warning"
        else:
            return "healthy"
    
    def _get_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary"""
        summary = {}
        
        # Key performance indicators
        kpi_metrics = [
            'cpu_usage_percent', 'memory_usage_percent', 
            'cache_hit_ratio', 'cache_access_time_ms',
            'process_startup_time_s', 'ipc_response_time_ms'
        ]
        
        for metric in kpi_metrics:
            if metric in self.current_metrics:
                summary[metric] = {
                    'current': self.current_metrics[metric],
                    'trend': self.current_metrics.get(f'{metric}_trend', {}).get('trend_direction', 'unknown')
                }
        
        return summary
    
    def _get_trend_summary(self) -> Dict[str, str]:
        """Get performance trend summary"""
        trend_summary = {}
        
        for metric_name, trend_data in self.current_metrics.items():
            if metric_name.endswith('_trend') and isinstance(trend_data, dict):
                base_metric = metric_name.replace('_trend', '')
                trend_summary[base_metric] = trend_data.get('trend_direction', 'unknown')
        
        return trend_summary
    
    async def _get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get optimization recommendations from all components"""
        recommendations = []
        
        # Cache recommendations
        if self.cache_manager:
            try:
                cache_recs = self.cache_manager.get_optimization_recommendations()
                recommendations.extend(cache_recs)
            except Exception as e:
                self.logger.warning(f"Failed to get cache recommendations: {e}")
        
        # Process recommendations
        if self.process_optimizer:
            try:
                process_recs = self.process_optimizer.get_optimization_recommendations()
                recommendations.extend(process_recs)
            except Exception as e:
                self.logger.warning(f"Failed to get process recommendations: {e}")
        
        # System-level recommendations based on current metrics
        system_recs = self._generate_system_recommendations()
        recommendations.extend(system_recs)
        
        return recommendations
    
    def _generate_system_recommendations(self) -> List[Dict[str, Any]]:
        """Generate system-level optimization recommendations"""
        recommendations = []
        
        # High memory usage recommendation
        memory_usage = self.current_metrics.get('memory_usage_percent', 0)
        if memory_usage > 85:
            recommendations.append({
                'category': 'system',
                'priority': 'high',
                'title': 'High Memory Usage Detected',
                'description': f'System memory usage is {memory_usage:.1f}%',
                'actions': [
                    'Review memory allocation patterns',
                    'Implement memory optimization strategies',
                    'Consider increasing system memory',
                    'Optimize cache sizes and TTL settings'
                ]
            })
        
        return recommendations
    
    def get_performance_dashboard(self) -> Dict[str, Any]:
        """Get current performance dashboard data"""
        return {
            'timestamp': datetime.now().isoformat(),
            'status': self._get_overall_status(),
            'metrics': self.current_metrics,
            'active_alerts': [asdict(alert) for alert in self.active_alerts.values()],
            'alert_count': len(self.active_alerts),
            'metrics_count': len(self.current_metrics),
            'monitoring_interval': self.monitoring_interval
        }
    
    async def run_performance_test(self) -> Dict[str, Any]:
        """Run comprehensive performance test"""
        self.logger.info("Running comprehensive performance test...")
        
        test_results = {
            'test_timestamp': datetime.now().isoformat(),
            'system_test': None,
            'cache_test': None,
            'overall_score': 0
        }
        
        # Cache performance test
        if self.cache_manager:
            try:
                cache_stats = self.cache_manager.get_performance_stats()
                test_results['cache_test'] = cache_stats
            except Exception as e:
                test_results['cache_test'] = {'error': str(e)}
        
        # System resource test
        if self.analyzer:
            try:
                system_results = await self.analyzer._analyze_system_resources()
                test_results['system_test'] = system_results
            except Exception as e:
                test_results['system_test'] = {'error': str(e)}
        
        # Calculate overall performance score
        test_results['overall_score'] = self._calculate_performance_score(test_results)
        
        self.logger.info(f"Performance test completed. Overall score: {test_results['overall_score']}/100")
        return test_results
    
    def _calculate_performance_score(self, test_results: Dict[str, Any]) -> int:
        """Calculate overall performance score (0-100)"""
        score = 100
        
        # Cache score (40 points)
        cache_test = test_results.get('cache_test', {})
        if 'error' in cache_test:
            score -= 20
        else:
            hit_ratio = cache_test.get('cache_hit_ratio', 0)
            if hit_ratio < 0.5:
                score -= 30
            elif hit_ratio < 0.8:
                score -= 15
        
        # System score (40 points)
        system_test = test_results.get('system_test', {})
        if 'error' in system_test:
            score -= 20
        else:
            memory_usage = system_test.get('memory', {}).get('usage_percent', 0)
            cpu_usage = system_test.get('cpu', {}).get('usage_percent', 0)
            
            if memory_usage > 90 or cpu_usage > 90:
                score -= 30
            elif memory_usage > 80 or cpu_usage > 80:
                score -= 15
        
        # Alert penalty (20 points)
        critical_alerts = sum(1 for alert in self.active_alerts.values() if alert.severity == 'critical')
        warning_alerts = sum(1 for alert in self.active_alerts.values() if alert.severity == 'warning')
        
        score -= (critical_alerts * 10 + warning_alerts * 5)
        
        return max(0, score)
    
    async def stop(self):
        """Stop monitoring and cleanup"""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self.dashboard_task:
            self.dashboard_task.cancel()
            try:
                await self.dashboard_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Performance monitoring stopped")


# Factory function
async def create_performance_monitor() -> PerformanceMonitor:
    """Create and initialize performance monitor"""
    monitor = PerformanceMonitor()
    await monitor.initialize()
    return monitor
