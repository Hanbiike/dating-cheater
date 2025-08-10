"""
Multi-tier Caching System

Implements Tier 2 caching optimization with Redis integration.
Provides in-memory → Redis → Database cascade with intelligent fallback.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Union, List, TypeVar, Generic
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib

import aioredis

from src.database.config import RedisConfig, load_redis_config
from src.utils.logger import setup_logger

T = TypeVar('T')


@dataclass
class CacheMetrics:
    """Cache performance metrics"""
    hits: int = 0
    misses: int = 0
    errors: int = 0
    total_requests: int = 0
    average_response_time: float = 0.0
    
    def hit_ratio(self) -> float:
        """Calculate cache hit ratio"""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests
    
    def miss_ratio(self) -> float:
        """Calculate cache miss ratio"""
        return 1.0 - self.hit_ratio()
    
    def error_ratio(self) -> float:
        """Calculate error ratio"""
        if self.total_requests == 0:
            return 0.0
        return self.errors / self.total_requests


class InMemoryCache:
    """
    Tier 1: In-Memory cache with LRU eviction
    Ultra-fast access for frequently used data
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.access_times: Dict[str, float] = {}
        self.logger = setup_logger(__name__)
        
    def _evict_lru(self):
        """Remove least recently used item if cache is full"""
        if len(self.cache) >= self.max_size:
            # Find least recently used key
            lru_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            self.cache.pop(lru_key, None)
            self.access_times.pop(lru_key, None)
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired"""
        if 'expires_at' not in entry:
            return False
        return time.time() > entry['expires_at']
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from in-memory cache"""
        if key not in self.cache:
            return None
            
        entry = self.cache[key]
        
        # Check expiration
        if self._is_expired(entry):
            self.cache.pop(key, None)
            self.access_times.pop(key, None)
            return None
        
        # Update access time
        self.access_times[key] = time.time()
        
        return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in in-memory cache"""
        try:
            self._evict_lru()
            
            ttl = ttl or self.default_ttl
            expires_at = time.time() + ttl
            
            self.cache[key] = {
                'value': value,
                'expires_at': expires_at,
                'created_at': time.time()
            }
            self.access_times[key] = time.time()
            
            return True
        except Exception as e:
            self.logger.error(f"Error setting in-memory cache key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from in-memory cache"""
        deleted = key in self.cache
        self.cache.pop(key, None)
        self.access_times.pop(key, None)
        return deleted
    
    def clear(self):
        """Clear all cache entries"""
        self.cache.clear()
        self.access_times.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        current_time = time.time()
        expired_count = sum(1 for entry in self.cache.values() 
                          if self._is_expired(entry))
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'expired_entries': expired_count,
            'memory_efficiency': 1.0 - (expired_count / max(len(self.cache), 1))
        }


class RedisCache:
    """
    Tier 2: Redis distributed cache
    Persistent cache layer with cross-instance sharing
    """
    
    def __init__(self, config: RedisConfig):
        self.config = config
        self.redis: Optional[aioredis.Redis] = None
        self.logger = setup_logger(__name__)
        self._is_connected = False
        
    async def connect(self) -> bool:
        """Connect to Redis server"""
        try:
            self.redis = aioredis.from_url(
                self.config.get_redis_url(),
                max_connections=self.config.max_connections,
                retry_on_timeout=self.config.retry_on_timeout,
                health_check_interval=self.config.health_check_interval,
                socket_keepalive=self.config.socket_keepalive,
                decode_responses=True
            )
            
            # Test connection
            await self.redis.ping()
            self._is_connected = True
            self.logger.info("Redis cache connected successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            self._is_connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Redis server"""
        if self.redis:
            await self.redis.close()
            self._is_connected = False
            self.logger.info("Redis cache disconnected")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache"""
        if not self._is_connected:
            return None
            
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
                
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # Return as string if not JSON
                return value
                
        except Exception as e:
            self.logger.error(f"Error getting Redis key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in Redis cache"""
        if not self._is_connected:
            return False
            
        try:
            # Serialize value
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, ensure_ascii=False)
            else:
                serialized_value = str(value)
            
            ttl = ttl or self.config.default_ttl
            
            result = await self.redis.setex(key, ttl, serialized_value)
            return result is True
            
        except Exception as e:
            self.logger.error(f"Error setting Redis key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from Redis cache"""
        if not self._is_connected:
            return False
            
        try:
            result = await self.redis.delete(key)
            return result > 0
        except Exception as e:
            self.logger.error(f"Error deleting Redis key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis"""
        if not self._is_connected:
            return False
            
        try:
            result = await self.redis.exists(key)
            return result > 0
        except Exception as e:
            self.logger.error(f"Error checking Redis key existence {key}: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear keys matching pattern"""
        if not self._is_connected:
            return 0
            
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                result = await self.redis.delete(*keys)
                return result
            return 0
        except Exception as e:
            self.logger.error(f"Error clearing Redis pattern {pattern}: {e}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis statistics"""
        if not self._is_connected:
            return {}
            
        try:
            info = await self.redis.info()
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'hit_ratio': self._calculate_hit_ratio(info)
            }
        except Exception as e:
            self.logger.error(f"Error getting Redis stats: {e}")
            return {}
    
    def _calculate_hit_ratio(self, info: Dict[str, Any]) -> float:
        """Calculate Redis hit ratio"""
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)
        total = hits + misses
        
        if total == 0:
            return 0.0
        
        return hits / total


class MultiTierCache:
    """
    Multi-tier caching system with intelligent fallback
    Implements Tier 1 (Memory) → Tier 2 (Redis) → Tier 3 (Database) cascade
    """
    
    def __init__(self, redis_config: Optional[RedisConfig] = None):
        self.memory_cache = InMemoryCache(max_size=1000, default_ttl=300)
        
        # Initialize Redis cache
        redis_config = redis_config or load_redis_config()
        self.redis_cache = RedisCache(redis_config)
        
        self.logger = setup_logger(__name__)
        self.metrics = CacheMetrics()
        
        # Cache key prefixes for organization
        self.prefixes = {
            'user': 'user:',
            'config': 'config:',
            'conversation': 'conv:',
            'analytics': 'analytics:',
            'session': 'session:'
        }
    
    async def initialize(self) -> bool:
        """Initialize cache system"""
        redis_connected = await self.redis_cache.connect()
        if not redis_connected:
            self.logger.warning("Redis cache unavailable, using memory-only caching")
        
        self.logger.info(f"Multi-tier cache initialized (Redis: {redis_connected})")
        return True
    
    async def shutdown(self):
        """Shutdown cache system"""
        await self.redis_cache.disconnect()
        self.memory_cache.clear()
        self.logger.info("Multi-tier cache shutdown complete")
    
    def _make_key(self, key_type: str, key: str) -> str:
        """Generate prefixed cache key"""
        prefix = self.prefixes.get(key_type, '')
        return f"{prefix}{key}"
    
    def _hash_key(self, key: str) -> str:
        """Generate hash for long keys"""
        if len(key) > 250:  # Redis key length limit
            return hashlib.md5(key.encode()).hexdigest()
        return key
    
    async def get(self, key_type: str, key: str, default: Any = None) -> Any:
        """
        Get value from multi-tier cache with cascade fallback
        
        Args:
            key_type: Type of cache key (user, config, etc.)
            key: Cache key
            default: Default value if not found
        """
        start_time = time.time()
        cache_key = self._make_key(key_type, key)
        hashed_key = self._hash_key(cache_key)
        
        try:
            self.metrics.total_requests += 1
            
            # Tier 1: Memory cache
            value = self.memory_cache.get(hashed_key)
            if value is not None:
                self.metrics.hits += 1
                self._update_response_time(start_time)
                return value
            
            # Tier 2: Redis cache
            value = await self.redis_cache.get(hashed_key)
            if value is not None:
                # Populate memory cache
                self.memory_cache.set(hashed_key, value, ttl=300)  # 5 minutes
                self.metrics.hits += 1
                self._update_response_time(start_time)
                return value
            
            # Cache miss
            self.metrics.misses += 1
            self._update_response_time(start_time)
            return default
            
        except Exception as e:
            self.metrics.errors += 1
            self.logger.error(f"Error getting cache key {cache_key}: {e}")
            return default
    
    async def set(self, key_type: str, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in multi-tier cache
        
        Args:
            key_type: Type of cache key (user, config, etc.)
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        cache_key = self._make_key(key_type, key)
        hashed_key = self._hash_key(cache_key)
        
        # Get TTL based on key type
        if ttl is None:
            ttl = self._get_default_ttl(key_type)
        
        success = True
        
        try:
            # Set in memory cache (Tier 1)
            memory_success = self.memory_cache.set(hashed_key, value, ttl=min(ttl, 300))
            
            # Set in Redis cache (Tier 2)
            redis_success = await self.redis_cache.set(hashed_key, value, ttl=ttl)
            
            success = memory_success or redis_success
            
            if not success:
                self.logger.warning(f"Failed to set cache key {cache_key}")
            
        except Exception as e:
            self.logger.error(f"Error setting cache key {cache_key}: {e}")
            success = False
        
        return success
    
    async def delete(self, key_type: str, key: str) -> bool:
        """Delete value from all cache tiers"""
        cache_key = self._make_key(key_type, key)
        hashed_key = self._hash_key(cache_key)
        
        memory_success = self.memory_cache.delete(hashed_key)
        redis_success = await self.redis_cache.delete(hashed_key)
        
        return memory_success or redis_success
    
    async def clear_pattern(self, key_type: str, pattern: str = "*") -> int:
        """Clear cache entries matching pattern"""
        cache_pattern = self._make_key(key_type, pattern)
        
        # Clear Redis pattern
        redis_count = await self.redis_cache.clear_pattern(cache_pattern)
        
        # Clear matching memory cache entries
        memory_keys = [k for k in self.memory_cache.cache.keys() 
                      if k.startswith(self.prefixes.get(key_type, ''))]
        memory_count = 0
        for key in memory_keys:
            if self.memory_cache.delete(key):
                memory_count += 1
        
        total_cleared = redis_count + memory_count
        self.logger.info(f"Cleared {total_cleared} cache entries for pattern {cache_pattern}")
        
        return total_cleared
    
    def _get_default_ttl(self, key_type: str) -> int:
        """Get default TTL for key type"""
        ttl_map = {
            'user': self.redis_cache.config.user_cache_ttl,
            'config': self.redis_cache.config.config_cache_ttl,
            'conversation': 1800,  # 30 minutes
            'analytics': self.redis_cache.config.analytics_cache_ttl,
            'session': 3600  # 1 hour
        }
        
        return ttl_map.get(key_type, self.redis_cache.config.default_ttl)
    
    def _update_response_time(self, start_time: float):
        """Update average response time metric"""
        response_time = time.time() - start_time
        
        # Simple moving average
        if self.metrics.total_requests == 1:
            self.metrics.average_response_time = response_time
        else:
            # Exponential moving average with alpha = 0.1
            alpha = 0.1
            self.metrics.average_response_time = (
                alpha * response_time + 
                (1 - alpha) * self.metrics.average_response_time
            )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive cache metrics"""
        memory_stats = self.memory_cache.get_stats()
        
        return {
            'tier1_memory': memory_stats,
            'tier2_redis': {'connected': self.redis_cache._is_connected},
            'performance': {
                'total_requests': self.metrics.total_requests,
                'hits': self.metrics.hits,
                'misses': self.metrics.misses,
                'errors': self.metrics.errors,
                'hit_ratio': self.metrics.hit_ratio(),
                'miss_ratio': self.metrics.miss_ratio(),
                'error_ratio': self.metrics.error_ratio(),
                'average_response_time_ms': self.metrics.average_response_time * 1000
            }
        }
    
    async def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed statistics from all cache tiers"""
        memory_stats = self.memory_cache.get_stats()
        redis_stats = await self.redis_cache.get_stats()
        performance_metrics = self.get_metrics()
        
        return {
            'memory_cache': memory_stats,
            'redis_cache': redis_stats,
            'overall_performance': performance_metrics['performance'],
            'cache_distribution': {
                'memory_entries': memory_stats['size'],
                'redis_connected': redis_stats.get('connected_clients', 0) > 0
            }
        }


# Factory function for easy initialization
async def create_cache_system(redis_config: Optional[RedisConfig] = None) -> MultiTierCache:
    """
    Factory function to create and initialize multi-tier cache system
    
    Args:
        redis_config: Optional Redis configuration (uses default if None)
        
    Returns:
        Initialized MultiTierCache instance
    """
    cache_system = MultiTierCache(redis_config)
    await cache_system.initialize()
    return cache_system
