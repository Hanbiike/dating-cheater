"""
Database Integration Module

Provides enterprise-grade database integration for the Han Dating Bot.
Implements hybrid JSON-PostgreSQL storage with intelligent caching
and gradual migration capabilities.

Components:
- hybrid_store: Core database abstraction with JSON fallback
- cache: Multi-tier caching (Memory + Redis + Database)
- integration: High-level integration manager
- girls_adapter: Seamless integration with existing GirlsManager
- config: Database and Redis configuration management
- test_integration: Comprehensive testing suite

Usage:
    # Initialize database integration
    from src.database.integration import init_database_integration
    
    await init_database_integration(
        bot_id="your_bot_id",
        enable_migration=False  # Start with JSON fallback
    )
    
    # Use database adapter with existing code
    from src.database.girls_adapter import create_database_adapter
    
    adapter = await create_database_adapter(girls_manager)
    profile = await adapter.load_profile(chat_id)
"""

from src.database.integration import (
    DatabaseIntegrationManager,
    init_database_integration,
    shutdown_database_integration,
    get_database_integration
)

from src.database.girls_adapter import (
    DatabaseGirlsAdapter,
    create_database_adapter
)

from src.database.hybrid_store import (
    HybridDataStore,
    DatabaseConnectionManager,
    create_database_store
)

from src.database.cache import (
    MultiTierCache,
    InMemoryCache,
    RedisCache,
    create_cache_system
)

from src.database.config import (
    DatabaseConfig,
    RedisConfig,
    load_database_config,
    load_redis_config,
    get_alembic_config
)

from src.database.test_integration import (
    DatabaseIntegrationTester,
    run_integration_tests,
    run_quick_smoke_test
)

__version__ = "1.0.0"
__author__ = "Han Dating Bot Team"

__all__ = [
    # Integration Manager
    "DatabaseIntegrationManager",
    "init_database_integration", 
    "shutdown_database_integration",
    "get_database_integration",
    
    # Adapters
    "DatabaseGirlsAdapter",
    "create_database_adapter",
    
    # Core Storage
    "HybridDataStore",
    "DatabaseConnectionManager", 
    "create_database_store",
    
    # Caching
    "MultiTierCache",
    "InMemoryCache",
    "RedisCache",
    "create_cache_system",
    
    # Configuration
    "DatabaseConfig",
    "RedisConfig",
    "load_database_config",
    "load_redis_config",
    "get_alembic_config",
    
    # Testing
    "DatabaseIntegrationTester",
    "run_integration_tests",
    "run_quick_smoke_test"
]
