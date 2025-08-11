"""
Smart Cache Implementation with Intelligent Warming

Enhances the existing multi-tier cache system with intelligent warming strategies,
usage pattern analysis, and performance optimization.
"""

import asyncio
import time
import json
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import hashlib

from src.database.cache import MultiTierCache, create_cache_system
from src.database.config import load_redis_config
from src.utils.logger import setup_logger


@dataclass
class CacheAccessPattern:
    """Tracks cache access patterns for intelligent warming"""
    key: str
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    access_times: deque = field(default_factory=lambda: deque(maxlen=100))
    average_interval: float = 0.0
    cache_hit_ratio: float = 0.0
    
    def record_access(self):
        """Record a cache access"""
        current_time = time.time()
        self.access_count += 1
        
        if self.access_times:
            interval = current_time - self.last_access
            self.access_times.append(interval)
            self.average_interval = sum(self.access_times) / len(self.access_times)
        
        self.last_access = current_time
    
    def predict_next_access(self) -> float:
        """Predict when the next access might occur"""
        if self.average_interval > 0:
            return self.last_access + self.average_interval
        return self.last_access + 300  # Default 5 minutes


@dataclass
class CacheWarmerConfig:
    """Configuration for cache warming strategies"""
    enable_predictive_warming: bool = True
    enable_usage_pattern_analysis: bool = True
    warming_threshold_accesses: int = 5  # Warm after 5 accesses
    warming_interval_minutes: int = 10   # Check every 10 minutes
    max_warm_keys_per_cycle: int = 50    # Limit warming load
    preload_popular_data: bool = True
    background_warming_enabled: bool = True


class SmartCacheManager:
    """Intelligent cache manager with warming and optimization"""
    
    def __init__(self, base_cache: MultiTierCache, config: CacheWarmerConfig = None):
        self.cache = base_cache
        self.config = config or CacheWarmerConfig()
        self.logger = setup_logger(__name__)
        
        # Pattern tracking
        self.access_patterns: Dict[str, CacheAccessPattern] = {}
        self.popular_keys: Set[str] = set()
        self.warming_queue: deque = deque()
        self.warming_task: Optional[asyncio.Task] = None
        
        # Performance tracking
        self.performance_metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'warming_hits': 0,  # Hits from warmed data
            'total_access_time': 0.0,
            'operations_count': 0
        }
        
        # Start background warming if enabled
        if self.config.background_warming_enabled:
            self._start_background_warming()
    
    async def get(self, key: str, default=None) -> Any:
        """Get value with pattern tracking and performance monitoring"""
        start_time = time.time()
        
        # Record access pattern
        self._record_access_pattern(key)
        
        # Get from cache
        value = await self.cache.get(key, default)
        
        # Update performance metrics
        access_time = time.time() - start_time
        self.performance_metrics['total_access_time'] += access_time
        self.performance_metrics['operations_count'] += 1
        
        if value is not None:
            self.performance_metrics['cache_hits'] += 1
            
            # Check if this was a warmed value
            if key in self.warming_queue:
                self.performance_metrics['warming_hits'] += 1
        else:
            self.performance_metrics['cache_misses'] += 1
        
        return value
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value with intelligent caching strategies"""
        # Set in cache
        result = await self.cache.set(key, value, ttl)
        
        # Update access pattern
        if key in self.access_patterns:
            self.access_patterns[key].record_access()
        
        # Add to popular keys if frequently accessed
        if key in self.access_patterns and self.access_patterns[key].access_count >= self.config.warming_threshold_accesses:
            self.popular_keys.add(key)
        
        return result
    
    def _record_access_pattern(self, key: str):
        """Record access pattern for a key"""
        if not self.config.enable_usage_pattern_analysis:
            return
        
        if key not in self.access_patterns:
            self.access_patterns[key] = CacheAccessPattern(key=key)
        
        self.access_patterns[key].record_access()
    
    async def warm_cache(self, keys: List[str], data_loader_func) -> int:
        """Manually warm cache with provided data loader function"""
        warmed_count = 0
        
        for key in keys:
            try:
                # Check if already cached
                if await self.cache.get(key) is not None:
                    continue
                
                # Load data
                data = await data_loader_func(key)
                if data is not None:
                    await self.cache.set(key, data, ttl=3600)  # 1 hour TTL
                    warmed_count += 1
                    self.warming_queue.append(key)
                    
            except Exception as e:
                self.logger.warning(f"Failed to warm cache for key {key}: {e}")
        
        self.logger.info(f"Cache warming completed: {warmed_count} keys warmed")
        return warmed_count
    
    async def _predictive_warming(self):
        """Predictively warm cache based on usage patterns"""
        if not self.config.enable_predictive_warming:
            return
        
        current_time = time.time()
        keys_to_warm = []
        
        for key, pattern in self.access_patterns.items():
            # Skip if not frequently accessed
            if pattern.access_count < self.config.warming_threshold_accesses:
                continue
            
            # Predict next access time
            predicted_access = pattern.predict_next_access()
            
            # Warm if prediction suggests access soon (within 2 intervals)
            if predicted_access - current_time < pattern.average_interval * 2:
                # Check if not already cached
                if await self.cache.get(key) is None:
                    keys_to_warm.append(key)
        
        if keys_to_warm:
            self.logger.info(f"Predictive warming identified {len(keys_to_warm)} keys for warming")
            # Note: In real implementation, you'd need a data loader function
            # self.warming_queue.extend(keys_to_warm)
    
    def _start_background_warming(self):
        """Start background warming task"""
        async def warming_loop():
            while True:
                try:
                    await self._predictive_warming()
                    await self._cleanup_old_patterns()
                    await asyncio.sleep(self.config.warming_interval_minutes * 60)
                except Exception as e:
                    self.logger.error(f"Background warming error: {e}")
                    await asyncio.sleep(60)  # Wait 1 minute on error
        
        self.warming_task = asyncio.create_task(warming_loop())
    
    async def _cleanup_old_patterns(self):
        """Clean up old access patterns to prevent memory bloat"""
        cutoff_time = time.time() - (24 * 3600)  # 24 hours ago
        
        old_keys = [
            key for key, pattern in self.access_patterns.items()
            if pattern.last_access < cutoff_time
        ]
        
        for key in old_keys:
            del self.access_patterns[key]
            self.popular_keys.discard(key)
        
        if old_keys:
            self.logger.info(f"Cleaned up {len(old_keys)} old access patterns")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        total_operations = self.performance_metrics['operations_count']
        
        if total_operations == 0:
            return {
                'cache_hit_ratio': 0.0,
                'warming_effectiveness': 0.0,
                'average_access_time_ms': 0.0,
                'total_operations': 0,
                'popular_keys_count': len(self.popular_keys),
                'tracked_patterns': len(self.access_patterns)
            }
        
        return {
            'cache_hit_ratio': self.performance_metrics['cache_hits'] / total_operations,
            'warming_effectiveness': self.performance_metrics['warming_hits'] / max(self.performance_metrics['cache_hits'], 1),
            'average_access_time_ms': (self.performance_metrics['total_access_time'] / total_operations) * 1000,
            'total_operations': total_operations,
            'popular_keys_count': len(self.popular_keys),
            'tracked_patterns': len(self.access_patterns),
            'cache_hits': self.performance_metrics['cache_hits'],
            'cache_misses': self.performance_metrics['cache_misses'],
            'warming_hits': self.performance_metrics['warming_hits']
        }
    
    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate cache optimization recommendations"""
        recommendations = []
        stats = self.get_performance_stats()
        
        # Low hit ratio recommendation
        if stats['cache_hit_ratio'] < 0.8:
            recommendations.append({
                'type': 'hit_ratio',
                'priority': 'high',
                'title': 'Improve Cache Hit Ratio',
                'description': f'Current hit ratio is {stats["cache_hit_ratio"]:.1%}, target is 80%+',
                'actions': [
                    'Increase cache TTL for stable data',
                    'Implement more aggressive cache warming',
                    'Review cache invalidation patterns',
                    'Consider increasing cache size'
                ]
            })
        
        # Slow access time recommendation
        if stats['average_access_time_ms'] > 10:
            recommendations.append({
                'type': 'performance',
                'priority': 'medium',
                'title': 'Optimize Cache Access Time',
                'description': f'Average access time is {stats["average_access_time_ms"]:.2f}ms, target is <10ms',
                'actions': [
                    'Optimize serialization/deserialization',
                    'Review network latency to Redis',
                    'Consider in-memory cache size increase',
                    'Implement connection pooling optimization'
                ]
            })
        
        # Low warming effectiveness
        if stats['warming_effectiveness'] < 0.3 and stats['warming_hits'] > 0:
            recommendations.append({
                'type': 'warming',
                'priority': 'low',
                'title': 'Improve Cache Warming Strategy',
                'description': f'Warming effectiveness is {stats["warming_effectiveness"]:.1%}',
                'actions': [
                    'Review predictive warming algorithms',
                    'Adjust warming thresholds',
                    'Implement more targeted warming strategies'
                ]
            })
        
        return recommendations
    
    async def stop(self):
        """Stop background tasks and cleanup"""
        if self.warming_task:
            self.warming_task.cancel()
            try:
                await self.warming_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Smart cache manager stopped")


async def create_smart_cache_system(redis_config=None) -> SmartCacheManager:
    """Factory function to create smart cache system"""
    if redis_config is None:
        redis_config = load_redis_config()
    
    base_cache = await create_cache_system(redis_config)
    smart_cache = SmartCacheManager(base_cache)
    
    return smart_cache


# Data loader functions for common cache warming scenarios
class CacheWarmingLoaders:
    """Common data loader functions for cache warming"""
    
    @staticmethod
    async def load_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
        """Load user profile data for cache warming"""
        # This would typically load from database
        # Placeholder implementation
        return {
            'user_id': user_id,
            'profile_data': f'profile_for_{user_id}',
            'loaded_at': time.time()
        }
    
    @staticmethod
    async def load_bot_configuration(bot_id: str) -> Optional[Dict[str, Any]]:
        """Load bot configuration for cache warming"""
        # This would typically load from configuration system
        return {
            'bot_id': bot_id,
            'config_data': f'config_for_{bot_id}',
            'loaded_at': time.time()
        }
