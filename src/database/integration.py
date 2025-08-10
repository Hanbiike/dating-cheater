"""
Database Integration Manager

Provides seamless integration between existing bot code and new database layer.
Implements Strangler Fig pattern for gradual migration from JSON to PostgreSQL.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from src.database.hybrid_store import HybridDataStore, create_database_store
from src.database.cache import MultiTierCache, create_cache_system
from src.database.config import DatabaseConfig, RedisConfig, load_database_config, load_redis_config
from src.utils.logger import setup_logger
from src.utils.exceptions import HanBotError


class DatabaseIntegrationManager:
    """
    Manages database integration and migration state.
    Provides high-level interface for bot components to use database features.
    """
    
    def __init__(self, bot_id: str = "default"):
        self.bot_id = bot_id
        self.logger = setup_logger(__name__)
        
        # Core components
        self.data_store: Optional[HybridDataStore] = None
        self.cache_system: Optional[MultiTierCache] = None
        
        # Integration state
        self._is_initialized = False
        self._migration_enabled = False
        self._components_migrated = {
            'users': False,
            'configuration': False,
            'conversations': False,
            'analytics': False
        }
        
        # Performance tracking
        self._db_metrics = {
            'queries_executed': 0,
            'cache_hits': 0,
            'fallback_to_json': 0,
            'errors': 0
        }
    
    async def initialize(self, enable_migration: bool = False) -> bool:
        """
        Initialize database integration system
        
        Args:
            enable_migration: Whether to enable database migration from start
            
        Returns:
            True if initialization successful
        """
        if self._is_initialized:
            return True
        
        try:
            self.logger.info(f"Initializing Database Integration Manager for bot: {self.bot_id}")
            
            # Initialize data store
            self.data_store = await create_database_store(self.bot_id)
            self.logger.info("✅ Database store initialized")
            
            # Initialize cache system
            self.cache_system = await create_cache_system()
            self.logger.info("✅ Cache system initialized")
            
            # Enable migration if requested
            if enable_migration:
                await self.enable_migration()
            
            self._is_initialized = True
            self.logger.info("🚀 Database Integration Manager ready")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Database Integration Manager: {e}")
            return False
    
    async def shutdown(self):
        """Gracefully shutdown database connections"""
        if not self._is_initialized:
            return
        
        try:
            if self.cache_system:
                await self.cache_system.shutdown()
                
            if self.data_store and self.data_store.db_manager:
                await self.data_store.db_manager.close()
            
            self._is_initialized = False
            self.logger.info("Database Integration Manager shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during database shutdown: {e}")
    
    # Migration Control Methods
    
    async def enable_migration(self, components: Optional[List[str]] = None) -> bool:
        """
        Enable database migration for specified components
        
        Args:
            components: List of components to migrate (None = all)
        """
        if not self._is_initialized:
            raise HanBotError("Database integration not initialized")
        
        components = components or ['users', 'configuration', 'conversations', 'analytics']
        
        try:
            for component in components:
                if component in self._components_migrated:
                    success = await self.data_store.enable_component_migration(component)
                    if success:
                        self._components_migrated[component] = True
                        self.logger.info(f"✅ Migration enabled for component: {component}")
                    else:
                        self.logger.error(f"❌ Failed to enable migration for: {component}")
            
            self._migration_enabled = any(self._components_migrated.values())
            self.logger.info(f"Migration status: {self._migration_enabled}")
            
            return self._migration_enabled
            
        except Exception as e:
            self.logger.error(f"Error enabling migration: {e}")
            return False
    
    async def disable_migration(self, components: Optional[List[str]] = None) -> bool:
        """
        Disable database migration for specified components (rollback to JSON)
        
        Args:
            components: List of components to rollback (None = all)
        """
        if not self._is_initialized:
            return False
        
        components = components or list(self._components_migrated.keys())
        
        try:
            for component in components:
                if component in self._components_migrated:
                    success = await self.data_store.disable_component_migration(component)
                    if success:
                        self._components_migrated[component] = False
                        self.logger.info(f"⬅️ Migration disabled for component: {component}")
            
            self._migration_enabled = any(self._components_migrated.values())
            return True
            
        except Exception as e:
            self.logger.error(f"Error disabling migration: {e}")
            return False
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get detailed migration status"""
        if not self._is_initialized:
            return {'status': 'not_initialized'}
        
        return {
            'enabled': self._migration_enabled,
            'components': self._components_migrated.copy(),
            'store_status': self.data_store.get_migration_status() if self.data_store else {},
            'metrics': self._db_metrics.copy()
        }
    
    # High-level User Data Methods
    
    async def get_user_profile(self, telegram_id: int, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get user profile with intelligent caching and fallback
        
        Args:
            telegram_id: Telegram user ID
            use_cache: Whether to use cache (default: True)
        """
        if not self._is_initialized:
            raise HanBotError("Database integration not initialized")
        
        cache_key = str(telegram_id)
        
        try:
            # Try cache first if enabled
            if use_cache and self.cache_system:
                cached_profile = await self.cache_system.get('user', cache_key)
                if cached_profile is not None:
                    self._db_metrics['cache_hits'] += 1
                    return cached_profile
            
            # Get from data store (with automatic fallback)
            profile = await self.data_store.get_user_profile(telegram_id)
            self._db_metrics['queries_executed'] += 1
            
            # Cache the result if found
            if profile and use_cache and self.cache_system:
                await self.cache_system.set('user', cache_key, profile)
            
            return profile
            
        except Exception as e:
            self._db_metrics['errors'] += 1
            self.logger.error(f"Error getting user profile {telegram_id}: {e}")
            return None
    
    async def save_user_profile(self, telegram_id: int, profile_data: Dict[str, Any]) -> bool:
        """
        Save user profile with caching and dual-write during migration
        
        Args:
            telegram_id: Telegram user ID
            profile_data: Profile data to save
        """
        if not self._is_initialized:
            raise HanBotError("Database integration not initialized")
        
        cache_key = str(telegram_id)
        
        try:
            # Save to data store
            success = await self.data_store.save_user_profile(telegram_id, profile_data)
            self._db_metrics['queries_executed'] += 1
            
            if success:
                # Update cache
                if self.cache_system:
                    await self.cache_system.set('user', cache_key, profile_data)
                
                return True
            else:
                self._db_metrics['fallback_to_json'] += 1
                return False
                
        except Exception as e:
            self._db_metrics['errors'] += 1
            self.logger.error(f"Error saving user profile {telegram_id}: {e}")
            return False
    
    async def update_user_activity(self, telegram_id: int) -> bool:
        """Update user's last activity timestamp"""
        if not self._is_initialized:
            return False
        
        try:
            # Get current profile
            profile = await self.get_user_profile(telegram_id, use_cache=False)
            if not profile:
                return False
            
            # Update activity timestamp
            profile['last_activity'] = datetime.now(timezone.utc).isoformat()
            
            # Save updated profile
            return await self.save_user_profile(telegram_id, profile)
            
        except Exception as e:
            self.logger.error(f"Error updating user activity {telegram_id}: {e}")
            return False
    
    # Configuration Methods
    
    async def get_bot_configuration(self, scope: str = "global", scope_id: Optional[str] = None) -> Dict[str, Any]:
        """Get bot configuration with caching"""
        if not self._is_initialized:
            raise HanBotError("Database integration not initialized")
        
        cache_key = f"{scope}:{scope_id or 'default'}"
        
        try:
            # Try cache first
            if self.cache_system:
                cached_config = await self.cache_system.get('config', cache_key)
                if cached_config is not None:
                    self._db_metrics['cache_hits'] += 1
                    return cached_config
            
            # Get from data store
            config = await self.data_store.get_bot_configuration(scope, scope_id)
            self._db_metrics['queries_executed'] += 1
            
            # Cache the result
            if config and self.cache_system:
                await self.cache_system.set('config', cache_key, config, ttl=7200)  # 2 hours
            
            return config
            
        except Exception as e:
            self._db_metrics['errors'] += 1
            self.logger.error(f"Error getting bot configuration {scope}:{scope_id}: {e}")
            return {}
    
    async def save_bot_configuration(self, config_data: Dict[str, Any], 
                                   scope: str = "global", scope_id: Optional[str] = None) -> bool:
        """Save bot configuration with cache invalidation"""
        if not self._is_initialized:
            raise HanBotError("Database integration not initialized")
        
        cache_key = f"{scope}:{scope_id or 'default'}"
        
        try:
            # Save to data store
            success = await self.data_store.save_bot_configuration(config_data, scope, scope_id)
            self._db_metrics['queries_executed'] += 1
            
            if success:
                # Update cache
                if self.cache_system:
                    await self.cache_system.set('config', cache_key, config_data, ttl=7200)
                
                return True
            else:
                self._db_metrics['fallback_to_json'] += 1
                return False
                
        except Exception as e:
            self._db_metrics['errors'] += 1
            self.logger.error(f"Error saving bot configuration {scope}:{scope_id}: {e}")
            return False
    
    # Analytics Methods
    
    async def log_analytics_event(self, event_type: str, event_data: Dict[str, Any],
                                dimensions: Optional[Dict[str, Any]] = None) -> bool:
        """Log analytics event with performance optimization"""
        if not self._is_initialized:
            return False
        
        try:
            success = await self.data_store.log_analytics_event(event_type, event_data, dimensions)
            self._db_metrics['queries_executed'] += 1
            
            if not success:
                self._db_metrics['fallback_to_json'] += 1
            
            return success
            
        except Exception as e:
            self._db_metrics['errors'] += 1
            self.logger.error(f"Error logging analytics event {event_type}: {e}")
            return False
    
    # Performance and Monitoring Methods
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        if not self._is_initialized:
            return {}
        
        try:
            cache_metrics = {}
            if self.cache_system:
                cache_metrics = await self.cache_system.get_detailed_stats()
            
            return {
                'database_integration': self._db_metrics.copy(),
                'cache_system': cache_metrics,
                'migration_status': self.get_migration_status(),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting performance metrics: {e}")
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on database components"""
        health_status = {
            'overall': 'unknown',
            'database_store': 'unknown',
            'cache_system': 'unknown',
            'migration_enabled': self._migration_enabled,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if not self._is_initialized:
            health_status['overall'] = 'not_initialized'
            return health_status
        
        try:
            # Check database store
            if self.data_store and self.data_store.db_manager:
                try:
                    # Simple connectivity test
                    await self.data_store.db_manager.execute_read_query("SELECT 1")
                    health_status['database_store'] = 'healthy'
                except:
                    health_status['database_store'] = 'unhealthy'
            
            # Check cache system
            if self.cache_system and self.cache_system.redis_cache:
                if self.cache_system.redis_cache._is_connected:
                    health_status['cache_system'] = 'healthy'
                else:
                    health_status['cache_system'] = 'disconnected'
            
            # Overall status
            if (health_status['database_store'] == 'healthy' and 
                health_status['cache_system'] in ['healthy', 'disconnected']):
                health_status['overall'] = 'healthy'
            else:
                health_status['overall'] = 'degraded'
            
        except Exception as e:
            self.logger.error(f"Error during health check: {e}")
            health_status['overall'] = 'error'
            health_status['error'] = str(e)
        
        return health_status


# Global instance for easy access throughout the application
db_integration: Optional[DatabaseIntegrationManager] = None


async def init_database_integration(bot_id: str = "default", enable_migration: bool = False) -> bool:
    """
    Initialize global database integration instance
    
    Args:
        bot_id: Bot identifier
        enable_migration: Whether to enable database migration
        
    Returns:
        True if initialization successful
    """
    global db_integration
    
    if db_integration is None:
        db_integration = DatabaseIntegrationManager(bot_id)
    
    return await db_integration.initialize(enable_migration)


async def shutdown_database_integration():
    """Shutdown global database integration instance"""
    global db_integration
    
    if db_integration:
        await db_integration.shutdown()
        db_integration = None


def get_database_integration() -> Optional[DatabaseIntegrationManager]:
    """Get global database integration instance"""
    return db_integration
