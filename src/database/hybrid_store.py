"""
Database Integration Layer - Core Database Operations

This module implements the hybrid JSON-relational database integration
following the creative phase designs. Provides seamless transition from
JSON storage to PostgreSQL with maintained compatibility.
"""

import asyncio
import asyncpg
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from contextlib import asynccontextmanager

from src.utils.logger import setup_logger
from src.config.config import Config


@dataclass
class DatabaseConfig:
    """Database configuration settings"""
    host: str = "localhost"
    port: int = 5432
    database: str = "dating_bot"
    username: str = "bot_user"
    password: str = ""
    max_connections: int = 20
    min_connections: int = 5
    command_timeout: int = 30
    
    def get_dsn(self) -> str:
        """Get PostgreSQL connection string"""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class DatabaseConnectionManager:
    """
    Advanced connection pooling with read/write separation
    Implements Tier 3 optimization from performance design
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.logger = setup_logger(__name__)
        self.write_pool: Optional[asyncpg.Pool] = None
        self.read_pool: Optional[asyncpg.Pool] = None
        self._is_initialized = False
    
    async def initialize(self):
        """Initialize connection pools"""
        if self._is_initialized:
            return
            
        try:
            # Write pool (primary database)
            self.write_pool = await asyncpg.create_pool(
                dsn=self.config.get_dsn(),
                min_size=self.config.min_connections,
                max_size=self.config.max_connections,
                command_timeout=self.config.command_timeout,
                max_queries=50000,
                max_inactive_connection_lifetime=300
            )
            
            # Read pool (can be read replica in production)
            self.read_pool = await asyncpg.create_pool(
                dsn=self.config.get_dsn(),  # Same DSN for now, can be replica
                min_size=max(2, self.config.min_connections // 2),
                max_size=max(10, self.config.max_connections // 2),
                command_timeout=self.config.command_timeout,
                max_queries=100000  # Read-heavy workload
            )
            
            self._is_initialized = True
            self.logger.info("Database connection pools initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database pools: {e}")
            raise
    
    async def close(self):
        """Close all connection pools"""
        if self.write_pool:
            await self.write_pool.close()
        if self.read_pool:
            await self.read_pool.close()
        self._is_initialized = False
        self.logger.info("Database connection pools closed")
    
    @asynccontextmanager
    async def get_read_connection(self):
        """Get read-only connection for queries"""
        if not self._is_initialized:
            await self.initialize()
        
        async with self.read_pool.acquire() as conn:
            yield conn
    
    @asynccontextmanager 
    async def get_write_connection(self):
        """Get write connection for modifications"""
        if not self._is_initialized:
            await self.initialize()
        
        async with self.write_pool.acquire() as conn:
            yield conn
    
    async def execute_read_query(self, query: str, *args) -> List[asyncpg.Record]:
        """Execute read-only query"""
        async with self.get_read_connection() as conn:
            return await conn.fetch(query, *args)
    
    async def execute_write_query(self, query: str, *args) -> str:
        """Execute write query"""
        async with self.get_write_connection() as conn:
            return await conn.execute(query, *args)
    
    async def execute_transaction(self, queries: List[tuple]) -> bool:
        """Execute multiple queries in transaction"""
        async with self.get_write_connection() as conn:
            async with conn.transaction():
                try:
                    for query, args in queries:
                        await conn.execute(query, *args)
                    return True
                except Exception as e:
                    self.logger.error(f"Transaction failed: {e}")
                    raise


class HybridDataStore:
    """
    Hybrid JSON-Relational data store implementing Strangler Fig pattern
    Supports dual-write during migration with automatic fallback
    """
    
    def __init__(self, db_manager: DatabaseConnectionManager, bot_id: str = "default"):
        self.db_manager = db_manager
        self.bot_id = bot_id
        self.logger = setup_logger(__name__)
        
        # Migration state flags
        self.users_migrated = False
        self.configuration_migrated = False
        self.conversations_migrated = False
        self.analytics_migrated = False
        
        # Fallback JSON storage paths
        self.json_paths = {
            'users': 'girls_data.json',
            'conversations': 'conversations/',
            'config': 'config.json'
        }
    
    async def get_user_profile(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user profile with intelligent fallback
        Implements Tier 2/3 optimization strategy
        """
        try:
            if self.users_migrated:
                # Try database first
                query = """
                    SELECT profile_data, preferences, created_at, updated_at
                    FROM users 
                    WHERE telegram_id = $1 AND status = 'active'
                """
                
                async with self.db_manager.get_read_connection() as conn:
                    result = await conn.fetchrow(query, telegram_id)
                    
                    if result:
                        return {
                            'telegram_id': telegram_id,
                            'profile': result['profile_data'],
                            'preferences': result['preferences'],
                            'created_at': result['created_at'].isoformat(),
                            'updated_at': result['updated_at'].isoformat()
                        }
            
            # Fallback to JSON
            return await self._get_user_from_json(telegram_id)
            
        except Exception as e:
            self.logger.error(f"Error getting user profile {telegram_id}: {e}")
            # Always fallback to JSON on database errors
            return await self._get_user_from_json(telegram_id)
    
    async def save_user_profile(self, telegram_id: int, profile_data: Dict[str, Any]) -> bool:
        """
        Save user profile with dual-write during migration
        Implements Strangler Fig pattern safety mechanism
        """
        success = True
        
        try:
            if self.users_migrated:
                # Primary: Database write
                query = """
                    INSERT INTO users (telegram_id, name, profile_data, preferences, updated_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (telegram_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        profile_data = EXCLUDED.profile_data,
                        preferences = EXCLUDED.preferences,
                        updated_at = NOW()
                """
                
                await self.db_manager.execute_write_query(
                    query,
                    telegram_id,
                    profile_data.get('name', ''),
                    json.dumps(profile_data.get('profile', {})),
                    json.dumps(profile_data.get('preferences', {}))
                )
                
                # During migration: Also write to JSON for safety
                if not self._is_migration_complete():
                    await self._save_user_to_json(telegram_id, profile_data)
            else:
                # JSON-only mode
                await self._save_user_to_json(telegram_id, profile_data)
                
        except Exception as e:
            self.logger.error(f"Error saving user profile {telegram_id}: {e}")
            success = False
            
            # Emergency fallback to JSON
            try:
                await self._save_user_to_json(telegram_id, profile_data)
                success = True
            except Exception as json_error:
                self.logger.error(f"JSON fallback also failed: {json_error}")
        
        return success
    
    async def get_bot_configuration(self, scope: str = "global", scope_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get configuration with multi-scope support
        Implements configuration hierarchy from schema design
        """
        try:
            if self.configuration_migrated:
                query = """
                    SELECT config_data
                    FROM configuration
                    WHERE scope = $1 AND scope_id = $2
                """
                
                result = await self.db_manager.execute_read_query(
                    query, scope, scope_id
                )
                
                if result:
                    return json.loads(result[0]['config_data'])
            
            # Fallback to JSON config
            return await self._get_config_from_json()
            
        except Exception as e:
            self.logger.error(f"Error getting configuration: {e}")
            return await self._get_config_from_json()
    
    async def save_bot_configuration(self, config_data: Dict[str, Any], 
                                   scope: str = "global", scope_id: Optional[str] = None) -> bool:
        """Save configuration with multi-scope support"""
        try:
            if self.configuration_migrated:
                query = """
                    INSERT INTO configuration (scope, scope_id, config_data, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (scope, scope_id) DO UPDATE SET
                        config_data = EXCLUDED.config_data,
                        updated_at = NOW()
                """
                
                await self.db_manager.execute_write_query(
                    query, scope, scope_id, json.dumps(config_data)
                )
                return True
            else:
                return await self._save_config_to_json(config_data)
                
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            return False
    
    async def log_analytics_event(self, event_type: str, event_data: Dict[str, Any],
                                dimensions: Optional[Dict[str, Any]] = None) -> bool:
        """Log analytics event with time-series optimization"""
        try:
            if self.analytics_migrated:
                query = """
                    INSERT INTO analytics_events (bot_id, event_type, event_data, dimensions, timestamp)
                    VALUES ((SELECT id FROM bot_instances WHERE name = $1), $2, $3, $4, NOW())
                """
                
                await self.db_manager.execute_write_query(
                    query,
                    self.bot_id,
                    event_type,
                    json.dumps(event_data),
                    json.dumps(dimensions or {})
                )
                return True
            else:
                # Simple JSON logging fallback
                return await self._log_to_json_file(event_type, event_data)
                
        except Exception as e:
            self.logger.error(f"Error logging analytics event: {e}")
            return False
    
    # Migration control methods
    
    async def enable_component_migration(self, component: str) -> bool:
        """Enable migration for specific component"""
        valid_components = ['users', 'configuration', 'conversations', 'analytics']
        
        if component not in valid_components:
            self.logger.error(f"Invalid component: {component}")
            return False
        
        setattr(self, f"{component}_migrated", True)
        self.logger.info(f"Migration enabled for component: {component}")
        return True
    
    async def disable_component_migration(self, component: str) -> bool:
        """Disable migration for specific component (rollback)"""
        valid_components = ['users', 'configuration', 'conversations', 'analytics']
        
        if component not in valid_components:
            self.logger.error(f"Invalid component: {component}")
            return False
        
        setattr(self, f"{component}_migrated", False)
        self.logger.info(f"Migration disabled for component: {component}")
        return True
    
    def _is_migration_complete(self) -> bool:
        """Check if all components are migrated"""
        return all([
            self.users_migrated,
            self.configuration_migrated,
            self.conversations_migrated,
            self.analytics_migrated
        ])
    
    def get_migration_status(self) -> Dict[str, bool]:
        """Get current migration status"""
        return {
            'users': self.users_migrated,
            'configuration': self.configuration_migrated,
            'conversations': self.conversations_migrated,
            'analytics': self.analytics_migrated,
            'complete': self._is_migration_complete()
        }
    
    # JSON fallback methods (private)
    
    async def _get_user_from_json(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Fallback method to get user from JSON storage"""
        try:
            with open(self.json_paths['users'], 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get(str(telegram_id))
        except FileNotFoundError:
            return None
        except Exception as e:
            self.logger.error(f"Error reading JSON user data: {e}")
            return None
    
    async def _save_user_to_json(self, telegram_id: int, profile_data: Dict[str, Any]) -> bool:
        """Fallback method to save user to JSON storage"""
        try:
            data = {}
            try:
                with open(self.json_paths['users'], 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                pass
            
            data[str(telegram_id)] = profile_data
            
            with open(self.json_paths['users'], 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            self.logger.error(f"Error saving JSON user data: {e}")
            return False
    
    async def _get_config_from_json(self) -> Dict[str, Any]:
        """Fallback method to get config from JSON"""
        try:
            with open(self.json_paths['config'], 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            self.logger.error(f"Error reading JSON config: {e}")
            return {}
    
    async def _save_config_to_json(self, config_data: Dict[str, Any]) -> bool:
        """Fallback method to save config to JSON"""
        try:
            with open(self.json_paths['config'], 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error saving JSON config: {e}")
            return False
    
    async def _log_to_json_file(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """Fallback method to log to JSON file"""
        try:
            log_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'bot_id': self.bot_id,
                'event_type': event_type,
                'event_data': event_data
            }
            
            log_file = f"analytics_{datetime.now().strftime('%Y%m')}.json"
            
            # Append to monthly log file
            logs = []
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except FileNotFoundError:
                pass
            
            logs.append(log_entry)
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            self.logger.error(f"Error logging to JSON file: {e}")
            return False


# Factory function for easy initialization
async def create_database_store(bot_id: str = "default") -> HybridDataStore:
    """
    Factory function to create and initialize database store
    with proper configuration and connection management
    """
    config = Config()
    
    # Initialize database configuration
    db_config = DatabaseConfig(
        host=getattr(config, 'DATABASE_HOST', 'localhost'),
        port=getattr(config, 'DATABASE_PORT', 5432),
        database=getattr(config, 'DATABASE_NAME', 'dating_bot'),
        username=getattr(config, 'DATABASE_USER', 'bot_user'),
        password=getattr(config, 'DATABASE_PASSWORD', ''),
        max_connections=getattr(config, 'DATABASE_MAX_CONNECTIONS', 20)
    )
    
    # Create connection manager
    db_manager = DatabaseConnectionManager(db_config)
    await db_manager.initialize()
    
    # Create hybrid data store
    data_store = HybridDataStore(db_manager, bot_id)
    
    return data_store
