"""
Performance Analysis Tool

Analyzes current system performance and identifies optimization opportunities.
"""

import asyncio
import time
import psutil
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import statistics

from src.database.hybrid_store import DatabaseConnectionManager, create_database_store
from src.database.cache import create_cache_system
from src.database.config import load_database_config, load_redis_config
from src.utils.logger import setup_logger


class PerformanceAnalyzer:
    """Analyzes system performance and identifies bottlenecks"""
    
    def __init__(self):
        self.logger = setup_logger(__name__)
        self.metrics: Dict[str, List[float]] = {
            'database_query_times': [],
            'cache_access_times': [],
            'memory_usage': [],
            'cpu_usage': []
        }
        
    async def run_performance_analysis(self) -> Dict[str, Any]:
        """Run comprehensive performance analysis"""
        self.logger.info("🔍 Starting performance analysis...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'database_performance': await self._analyze_database_performance(),
            'cache_performance': await self._analyze_cache_performance(),
            'system_resources': await self._analyze_system_resources(),
            'baseline_metrics': await self._establish_baseline_metrics(),
            'bottlenecks': [],
            'recommendations': []
        }
        
        # Identify bottlenecks
        results['bottlenecks'] = self._identify_bottlenecks(results)
        results['recommendations'] = self._generate_recommendations(results)
        
        self.logger.info("✅ Performance analysis complete")
        return results
    
    async def _analyze_database_performance(self) -> Dict[str, Any]:
        """Analyze database connection and query performance"""
        self.logger.info("📊 Analyzing database performance...")
        
        try:
            db_config = load_database_config()
            connection_manager = DatabaseConnectionManager(db_config)
            
            # Test connection initialization time
            start_time = time.time()
            await connection_manager.initialize()
            init_time = (time.time() - start_time) * 1000
            
            # Test query performance
            query_times = []
            for i in range(10):
                start_time = time.time()
                try:
                    result = await connection_manager.execute_read_query(
                        "SELECT 1 as test_query"
                    )
                    query_time = (time.time() - start_time) * 1000
                    query_times.append(query_time)
                except Exception as e:
                    self.logger.warning(f"Query test {i} failed: {e}")
            
            # Test connection pool status
            read_pool_size = connection_manager.read_pool.get_size() if connection_manager.read_pool else 0
            write_pool_size = connection_manager.write_pool.get_size() if connection_manager.write_pool else 0
            
            await connection_manager.close()
            
            return {
                'initialization_time_ms': init_time,
                'average_query_time_ms': statistics.mean(query_times) if query_times else None,
                'min_query_time_ms': min(query_times) if query_times else None,
                'max_query_time_ms': max(query_times) if query_times else None,
                'query_times': query_times,
                'read_pool_size': read_pool_size,
                'write_pool_size': write_pool_size,
                'connection_config': {
                    'min_pool_size': db_config.min_pool_size,
                    'max_pool_size': db_config.max_pool_size,
                    'command_timeout': db_config.command_timeout
                }
            }
            
        except Exception as e:
            self.logger.error(f"Database performance analysis failed: {e}")
            return {'error': str(e)}
    
    async def _analyze_cache_performance(self) -> Dict[str, Any]:
        """Analyze cache system performance"""
        self.logger.info("🚀 Analyzing cache performance...")
        
        try:
            redis_config = load_redis_config()
            cache_system = await create_cache_system(redis_config)
            
            # Test cache operations
            test_data = {'test_key': 'test_value', 'timestamp': time.time()}
            
            # Memory cache performance
            memory_times = []
            for i in range(100):
                start_time = time.time()
                await cache_system.memory_cache.set(f'test_{i}', test_data, ttl=60)
                value = await cache_system.memory_cache.get(f'test_{i}')
                memory_times.append((time.time() - start_time) * 1000)
            
            # Redis cache performance (if available)
            redis_times = []
            redis_available = False
            try:
                for i in range(10):
                    start_time = time.time()
                    await cache_system.redis_cache.set(f'test_{i}', test_data, ttl=60)
                    value = await cache_system.redis_cache.get(f'test_{i}')
                    redis_times.append((time.time() - start_time) * 1000)
                redis_available = True
            except Exception as e:
                self.logger.warning(f"Redis cache not available: {e}")
            
            # Get cache statistics
            memory_stats = cache_system.memory_cache.get_stats()
            
            return {
                'memory_cache': {
                    'average_time_ms': statistics.mean(memory_times),
                    'min_time_ms': min(memory_times),
                    'max_time_ms': max(memory_times),
                    'stats': memory_stats
                },
                'redis_cache': {
                    'available': redis_available,
                    'average_time_ms': statistics.mean(redis_times) if redis_times else None,
                    'min_time_ms': min(redis_times) if redis_times else None,
                    'max_time_ms': max(redis_times) if redis_times else None
                }
            }
            
        except Exception as e:
            self.logger.error(f"Cache performance analysis failed: {e}")
            return {'error': str(e)}
    
    async def _analyze_system_resources(self) -> Dict[str, Any]:
        """Analyze system resource usage"""
        self.logger.info("💻 Analyzing system resources...")
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Memory usage
        memory = psutil.virtual_memory()
        
        # Disk usage
        disk = psutil.disk_usage('/')
        
        return {
            'cpu': {
                'usage_percent': cpu_percent,
                'core_count': cpu_count,
                'load_average': list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
            },
            'memory': {
                'total_gb': round(memory.total / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2),
                'usage_percent': memory.percent,
                'free_gb': round(memory.free / (1024**3), 2)
            },
            'disk': {
                'total_gb': round(disk.total / (1024**3), 2),
                'free_gb': round(disk.free / (1024**3), 2),
                'usage_percent': round((disk.used / disk.total) * 100, 2)
            }
        }
    
    async def _establish_baseline_metrics(self) -> Dict[str, Any]:
        """Establish baseline performance metrics"""
        self.logger.info("📏 Establishing baseline metrics...")
        
        return {
            'target_response_times': {
                'memory_cache_ms': 1.0,
                'redis_cache_ms': 5.0,
                'database_query_ms': 50.0
            },
            'target_throughput': {
                'queries_per_second': 1000,
                'cache_operations_per_second': 10000
            },
            'resource_limits': {
                'max_cpu_percent': 80,
                'max_memory_percent': 80,
                'max_connections': 50
            }
        }
    
    def _identify_bottlenecks(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks"""
        bottlenecks = []
        
        # Database bottlenecks
        db_perf = results.get('database_performance', {})
        if db_perf.get('average_query_time_ms', 0) > 50:
            bottlenecks.append({
                'type': 'database',
                'issue': 'slow_queries',
                'current_value': db_perf.get('average_query_time_ms'),
                'target_value': 50,
                'severity': 'high' if db_perf.get('average_query_time_ms', 0) > 100 else 'medium'
            })
        
        # Cache bottlenecks
        cache_perf = results.get('cache_performance', {})
        if not cache_perf.get('redis_cache', {}).get('available', False):
            bottlenecks.append({
                'type': 'cache',
                'issue': 'redis_unavailable',
                'severity': 'medium',
                'impact': 'falling_back_to_memory_cache_only'
            })
        
        # Resource bottlenecks
        system_resources = results.get('system_resources', {})
        if system_resources.get('memory', {}).get('usage_percent', 0) > 80:
            bottlenecks.append({
                'type': 'system',
                'issue': 'high_memory_usage',
                'current_value': system_resources.get('memory', {}).get('usage_percent'),
                'target_value': 80,
                'severity': 'high'
            })
        
        return bottlenecks
    
    def _generate_recommendations(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate optimization recommendations"""
        recommendations = []
        
        # Database optimization recommendations
        db_perf = results.get('database_performance', {})
        if db_perf.get('average_query_time_ms', 0) > 50:
            recommendations.append({
                'category': 'database',
                'priority': 'high',
                'title': 'Optimize Database Query Performance',
                'description': 'Database queries are slower than target 50ms',
                'actions': [
                    'Increase connection pool size',
                    'Add query result caching',
                    'Optimize frequently used queries',
                    'Consider read replicas for read-heavy workloads'
                ]
            })
        
        # Cache optimization recommendations
        cache_perf = results.get('cache_performance', {})
        if not cache_perf.get('redis_cache', {}).get('available', False):
            recommendations.append({
                'category': 'cache',
                'priority': 'medium',
                'title': 'Enable Redis Distributed Cache',
                'description': 'Redis cache not available, limiting cache effectiveness',
                'actions': [
                    'Install and configure Redis server',
                    'Update Redis configuration',
                    'Test Redis connectivity',
                    'Implement cache warming strategies'
                ]
            })
        
        # Connection pool optimization
        if db_perf.get('read_pool_size', 0) < 10:
            recommendations.append({
                'category': 'database',
                'priority': 'medium',
                'title': 'Optimize Connection Pool Configuration',
                'description': 'Connection pool sizes may be suboptimal for performance',
                'actions': [
                    'Increase read pool size for read-heavy workloads',
                    'Optimize connection pool timeouts',
                    'Implement connection health monitoring',
                    'Consider separate pools for different query types'
                ]
            })
        
        return recommendations


async def main():
    """Run performance analysis"""
    analyzer = PerformanceAnalyzer()
    results = await analyzer.run_performance_analysis()
    
    # Save results to file
    output_file = f"performance_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Performance analysis complete. Results saved to {output_file}")
    print("\n📊 Summary:")
    
    # Print key metrics
    db_perf = results.get('database_performance', {})
    if 'average_query_time_ms' in db_perf:
        print(f"Database query time: {db_perf['average_query_time_ms']:.2f}ms")
    
    cache_perf = results.get('cache_performance', {})
    if 'memory_cache' in cache_perf:
        print(f"Memory cache time: {cache_perf['memory_cache']['average_time_ms']:.3f}ms")
    
    # Print bottlenecks
    bottlenecks = results.get('bottlenecks', [])
    if bottlenecks:
        print(f"\n⚠️ Found {len(bottlenecks)} bottlenecks:")
        for bottleneck in bottlenecks:
            print(f"  - {bottleneck['type']}: {bottleneck['issue']}")
    
    # Print recommendations
    recommendations = results.get('recommendations', [])
    if recommendations:
        print(f"\n💡 {len(recommendations)} optimization recommendations generated")


if __name__ == "__main__":
    asyncio.run(main())
