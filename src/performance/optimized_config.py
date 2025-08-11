"""
Enhanced Database Configuration for Performance Optimization

Provides optimized database configuration settings for improved performance
based on multi-bot production system requirements.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from pathlib import Path

from src.database.config import DatabaseConfig


@dataclass
class OptimizedDatabaseConfig(DatabaseConfig):
    """Enhanced database configuration optimized for performance"""
    
    # Optimized connection pool settings for multi-bot architecture
    min_pool_size: int = field(default=10)  # Increased from 5
    max_pool_size: int = field(default=50)  # Increased from 20
    pool_timeout: int = field(default=20)   # Reduced from 30 for faster response
    pool_recycle: int = field(default=1800) # Reduced from 3600 for fresher connections
    pool_pre_ping: bool = field(default=True)
    
    # Enhanced performance settings
    command_timeout: int = field(default=20)  # Reduced from 30
    server_side_cursors: bool = field(default=True)
    prepared_statement_cache_size: int = field(default=500)  # Increased from 100
    
    # Multi-process optimization settings
    connection_health_check_interval: int = field(default=30)
    max_queries_per_connection: int = field(default=100000)
    max_inactive_connection_lifetime: int = field(default=300)
    
    # Read replica settings for read/write separation
    read_replica_enabled: bool = field(default=False)
    read_replica_host: Optional[str] = field(default=None)
    read_replica_port: Optional[int] = field(default=None)
    
    # Query optimization settings
    enable_query_cache: bool = field(default=True)
    query_cache_size: int = field(default=1000)
    enable_query_monitoring: bool = field(default=True)
    slow_query_threshold_ms: int = field(default=100)
    
    # Connection prioritization
    high_priority_pool_percentage: float = field(default=0.3)  # 30% for high-priority operations
    
    def get_optimized_asyncpg_config(self) -> Dict[str, Any]:
        """Get optimized configuration for asyncpg connection pools"""
        base_config = self.get_asyncpg_config()
        
        # Add performance optimizations
        optimizations = {
            'max_queries': self.max_queries_per_connection,
            'max_inactive_connection_lifetime': self.max_inactive_connection_lifetime,
            'setup': self._setup_connection_optimizations
        }
        
        base_config.update(optimizations)
        return base_config
    
    def get_read_pool_config(self) -> Dict[str, Any]:
        """Get configuration for read-only connection pool"""
        config = self.get_optimized_asyncpg_config()
        
        # Use read replica if configured
        if self.read_replica_enabled and self.read_replica_host:
            config['host'] = self.read_replica_host
            if self.read_replica_port:
                config['port'] = self.read_replica_port
        
        # Optimize for read-heavy workload
        config['max_queries'] = self.max_queries_per_connection * 2
        
        return config
    
    def get_write_pool_config(self) -> Dict[str, Any]:
        """Get configuration for write connection pool"""
        config = self.get_optimized_asyncpg_config()
        
        # Optimize for write operations
        config['max_queries'] = self.max_queries_per_connection
        
        return config
    
    async def _setup_connection_optimizations(self, connection):
        """Setup connection-level optimizations"""
        try:
            # Enable prepared statement caching
            await connection.execute(f'SET max_prepared_transactions TO {self.prepared_statement_cache_size}')
            
            # Optimize work memory for complex queries
            await connection.execute('SET work_mem TO \'32MB\'')
            
            # Enable parallel query execution
            await connection.execute('SET max_parallel_workers_per_gather TO 4')
            
            # Optimize shared buffers usage
            await connection.execute('SET effective_cache_size TO \'1GB\'')
            
            # Enable query plan caching
            await connection.execute('SET plan_cache_mode TO auto')
            
        except Exception as e:
            # Log but don't fail on optimization setup
            print(f"Warning: Could not apply connection optimizations: {e}")
    
    def get_performance_monitoring_config(self) -> Dict[str, Any]:
        """Get configuration for performance monitoring"""
        return {
            'enable_monitoring': self.enable_query_monitoring,
            'slow_query_threshold_ms': self.slow_query_threshold_ms,
            'cache_size': self.query_cache_size,
            'health_check_interval': self.connection_health_check_interval
        }


def load_optimized_database_config() -> OptimizedDatabaseConfig:
    """Load optimized database configuration"""
    return OptimizedDatabaseConfig()


def get_multi_bot_pool_sizes(num_bots: int = 4) -> Dict[str, int]:
    """Calculate optimal pool sizes for multi-bot architecture"""
    base_config = load_optimized_database_config()
    
    # Calculate per-bot pool allocation
    total_read_connections = base_config.max_pool_size
    total_write_connections = max(10, base_config.max_pool_size // 3)
    
    return {
        'read_pool_per_bot': max(2, total_read_connections // num_bots),
        'write_pool_per_bot': max(1, total_write_connections // num_bots),
        'shared_read_pool': max(10, total_read_connections // 2),
        'shared_write_pool': max(5, total_write_connections // 2),
        'high_priority_pool': max(5, int(base_config.max_pool_size * base_config.high_priority_pool_percentage))
    }


# Performance tuning presets
class PerformancePresets:
    """Predefined performance configuration presets"""
    
    @staticmethod
    def development() -> OptimizedDatabaseConfig:
        """Configuration optimized for development environment"""
        return OptimizedDatabaseConfig(
            min_pool_size=3,
            max_pool_size=10,
            command_timeout=30,
            environment="development"
        )
    
    @staticmethod
    def staging() -> OptimizedDatabaseConfig:
        """Configuration optimized for staging environment"""
        return OptimizedDatabaseConfig(
            min_pool_size=5,
            max_pool_size=25,
            command_timeout=25,
            environment="staging"
        )
    
    @staticmethod
    def production() -> OptimizedDatabaseConfig:
        """Configuration optimized for production environment"""
        return OptimizedDatabaseConfig(
            min_pool_size=15,
            max_pool_size=75,
            command_timeout=15,
            read_replica_enabled=True,
            environment="production"
        )
    
    @staticmethod
    def high_performance() -> OptimizedDatabaseConfig:
        """Configuration optimized for maximum performance"""
        return OptimizedDatabaseConfig(
            min_pool_size=25,
            max_pool_size=100,
            command_timeout=10,
            pool_timeout=10,
            pool_recycle=900,
            prepared_statement_cache_size=1000,
            max_queries_per_connection=200000,
            read_replica_enabled=True,
            environment="production"
        )
