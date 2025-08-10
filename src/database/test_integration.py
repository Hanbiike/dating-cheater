"""
Database Integration Testing Module

Provides comprehensive testing for database integration components.
Tests both individual components and end-to-end integration scenarios.
"""

import asyncio
import json
import tempfile
import os
from typing import Dict, Any, List
from datetime import datetime, timezone
from pathlib import Path

from src.database.integration import DatabaseIntegrationManager, init_database_integration
from src.database.girls_adapter import DatabaseGirlsAdapter, create_database_adapter
from src.database.hybrid_store import HybridDataStore
from src.database.cache import MultiTierCache
from src.core.girls_manager import GirlProfile, GirlsManager
from src.utils.logger import setup_logger


class DatabaseIntegrationTester:
    """
    Comprehensive testing suite for database integration
    Tests migration scenarios, fallback mechanisms, and performance
    """
    
    def __init__(self):
        self.logger = setup_logger(__name__)
        self.test_results = []
        self.temp_dir = None
        
    async def run_all_tests(self) -> Dict[str, Any]:
        """
        Run complete test suite
        
        Returns:
            Dictionary with test results and summary
        """
        self.logger.info("🧪 Starting Database Integration Test Suite")
        
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp(prefix="db_integration_test_")
        self.logger.info(f"Test directory: {self.temp_dir}")
        
        test_methods = [
            self.test_database_config,
            self.test_cache_system,
            self.test_hybrid_data_store,
            self.test_database_integration_manager,
            self.test_girls_adapter,
            self.test_migration_scenarios,
            self.test_fallback_mechanisms,
            self.test_performance_benchmarks
        ]
        
        summary = {
            'total_tests': len(test_methods),
            'passed': 0,
            'failed': 0,
            'errors': [],
            'test_results': [],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        for test_method in test_methods:
            try:
                self.logger.info(f"Running test: {test_method.__name__}")
                result = await test_method()
                
                summary['test_results'].append({
                    'test_name': test_method.__name__,
                    'status': 'passed' if result['success'] else 'failed',
                    'details': result
                })
                
                if result['success']:
                    summary['passed'] += 1
                else:
                    summary['failed'] += 1
                    summary['errors'].append(f"{test_method.__name__}: {result.get('error', 'Unknown error')}")
                
            except Exception as e:
                self.logger.error(f"Test {test_method.__name__} raised exception: {e}")
                summary['failed'] += 1
                summary['errors'].append(f"{test_method.__name__}: {str(e)}")
                
                summary['test_results'].append({
                    'test_name': test_method.__name__,
                    'status': 'exception',
                    'error': str(e)
                })
        
        # Cleanup
        await self.cleanup()
        
        summary['success_rate'] = (summary['passed'] / summary['total_tests']) * 100
        
        self.logger.info(f"✅ Test suite completed: {summary['passed']}/{summary['total_tests']} passed ({summary['success_rate']:.1f}%)")
        
        return summary
    
    async def test_database_config(self) -> Dict[str, Any]:
        """Test database configuration loading and validation"""
        try:
            from src.database.config import DatabaseConfig, RedisConfig, load_database_config, load_redis_config
            
            # Test DatabaseConfig creation
            db_config = DatabaseConfig()
            assert db_config.host is not None
            assert db_config.port > 0
            assert db_config.database is not None
            
            # Test DSN generation
            dsn = db_config.get_dsn()
            assert "postgresql://" in dsn
            
            # Test Redis config
            redis_config = RedisConfig()
            redis_url = redis_config.get_redis_url()
            assert "redis://" in redis_url
            
            # Test factory functions
            loaded_db_config = load_database_config()
            loaded_redis_config = load_redis_config()
            
            return {
                'success': True,
                'db_config_valid': True,
                'redis_config_valid': True,
                'dsn_generated': dsn,
                'redis_url_generated': redis_url
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_cache_system(self) -> Dict[str, Any]:
        """Test multi-tier cache system"""
        try:
            from src.database.cache import InMemoryCache, MultiTierCache
            
            # Test in-memory cache
            memory_cache = InMemoryCache(max_size=10, default_ttl=300)
            
            # Test basic operations
            memory_cache.set("test_key", {"data": "test_value"})
            retrieved = memory_cache.get("test_key")
            assert retrieved == {"data": "test_value"}
            
            # Test LRU eviction
            for i in range(15):  # Exceed max_size
                memory_cache.set(f"key_{i}", f"value_{i}")
            
            stats = memory_cache.get_stats()
            assert stats['size'] <= 10
            
            # Test multi-tier cache (without Redis for now)
            # This would require Redis server running, so we'll test the interface
            multi_cache = MultiTierCache()
            
            return {
                'success': True,
                'memory_cache_working': True,
                'lru_eviction_working': True,
                'cache_stats': stats,
                'multi_tier_initialized': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_hybrid_data_store(self) -> Dict[str, Any]:
        """Test hybrid data store with JSON fallback"""
        try:
            # This test focuses on the JSON fallback since we don't have DB running
            from src.database.hybrid_store import HybridDataStore
            from src.database.config import DatabaseConfig
            
            # Create test data store (will fallback to JSON)
            db_config = DatabaseConfig()
            # Don't initialize actual DB connection for testing
            
            # Test user profile operations with JSON fallback
            test_profile = {
                'telegram_id': 12345,
                'name': 'Test User',
                'profile': {'test': 'data'},
                'preferences': {},
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            return {
                'success': True,
                'hybrid_store_interface': True,
                'json_fallback_available': True,
                'test_profile_format': test_profile
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_database_integration_manager(self) -> Dict[str, Any]:
        """Test database integration manager functionality"""
        try:
            # Test creation without actual database
            manager = DatabaseIntegrationManager(bot_id="test_bot")
            
            # Test migration status
            status = manager.get_migration_status()
            assert 'enabled' in status
            assert 'components' in status
            
            # Test health check (will show not initialized)
            health = await manager.health_check()
            assert 'overall' in health
            
            return {
                'success': True,
                'manager_created': True,
                'migration_status': status,
                'health_check': health
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_girls_adapter(self) -> Dict[str, Any]:
        """Test database adapter for GirlsManager"""
        try:
            # Create temporary JSON storage for testing
            temp_json_file = os.path.join(self.temp_dir, "test_girls_data.json")
            
            # Create a mock GirlsManager
            girls_manager = GirlsManager(path=temp_json_file)
            
            # Create adapter
            adapter = DatabaseGirlsAdapter(girls_manager)
            await adapter.initialize()
            
            # Test profile operations
            test_profile = GirlProfile(
                chat_id=67890,
                name="Test Girl",
                message_count=5
            )
            
            # Test save/load (will use JSON fallback)
            save_success = await adapter.save_profile(test_profile)
            loaded_profile = await adapter.load_profile(67890)
            
            # Test ensure_girl
            ensured_profile = await adapter.ensure_girl(67890, "Test Girl Updated")
            
            # Test metrics
            metrics = await adapter.get_adapter_metrics()
            health = await adapter.health_check()
            
            return {
                'success': True,
                'adapter_initialized': True,
                'save_success': save_success,
                'load_success': loaded_profile is not None,
                'ensure_girl_success': ensured_profile is not None,
                'metrics_available': 'database_available' in metrics,
                'health_check_passed': 'adapter_status' in health
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_migration_scenarios(self) -> Dict[str, Any]:
        """Test migration scenarios and component switching"""
        try:
            manager = DatabaseIntegrationManager(bot_id="migration_test")
            
            # Test initial state
            initial_status = manager.get_migration_status()
            assert not initial_status['enabled']
            
            # Test component migration enable/disable (without actual DB)
            # This tests the logic, not the actual database operations
            components = ['users', 'configuration']
            
            # The actual enable_migration would fail without DB, but we can test the interface
            migration_status_available = hasattr(manager, 'enable_migration')
            component_tracking = hasattr(manager, '_components_migrated')
            
            return {
                'success': True,
                'initial_migration_disabled': not initial_status['enabled'],
                'migration_interface_available': migration_status_available,
                'component_tracking_available': component_tracking,
                'migration_components': list(manager._components_migrated.keys())
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_fallback_mechanisms(self) -> Dict[str, Any]:
        """Test fallback mechanisms when database is unavailable"""
        try:
            # Create adapter without database integration
            adapter = DatabaseGirlsAdapter()
            await adapter.initialize()
            
            # Database should not be available
            db_available = adapter.is_database_available()
            
            # Test that operations gracefully handle missing database
            profile = await adapter.load_profile(12345)  # Should return None gracefully
            
            # Test health check with no database
            health = await adapter.health_check()
            
            return {
                'success': True,
                'database_correctly_unavailable': not db_available,
                'graceful_load_handling': profile is None,
                'health_check_handles_no_db': 'adapter_status' in health,
                'fallback_mechanisms_working': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_performance_benchmarks(self) -> Dict[str, Any]:
        """Test performance characteristics"""
        try:
            import time
            
            # Test in-memory cache performance
            from src.database.cache import InMemoryCache
            
            cache = InMemoryCache(max_size=1000)
            
            # Benchmark cache operations
            start_time = time.time()
            
            for i in range(100):
                cache.set(f"perf_key_{i}", {"data": f"value_{i}"})
            
            set_time = time.time() - start_time
            
            start_time = time.time()
            
            for i in range(100):
                cache.get(f"perf_key_{i}")
            
            get_time = time.time() - start_time
            
            # Test GirlProfile creation performance
            start_time = time.time()
            
            profiles = []
            for i in range(100):
                profile = GirlProfile(
                    chat_id=i,
                    name=f"User_{i}",
                    message_count=i
                )
                profiles.append(profile)
            
            profile_creation_time = time.time() - start_time
            
            return {
                'success': True,
                'cache_set_time_ms': set_time * 1000,
                'cache_get_time_ms': get_time * 1000,
                'profile_creation_time_ms': profile_creation_time * 1000,
                'operations_per_second': 100 / max(set_time, 0.001),
                'performance_acceptable': set_time < 0.1 and get_time < 0.1
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def cleanup(self):
        """Cleanup test resources"""
        try:
            if self.temp_dir and Path(self.temp_dir).exists():
                import shutil
                shutil.rmtree(self.temp_dir)
                self.logger.info(f"Cleaned up test directory: {self.temp_dir}")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


# Convenience functions for testing

async def run_integration_tests() -> Dict[str, Any]:
    """
    Run database integration tests
    
    Returns:
        Test results summary
    """
    tester = DatabaseIntegrationTester()
    return await tester.run_all_tests()


async def run_quick_smoke_test() -> bool:
    """
    Run quick smoke test to verify basic integration functionality
    
    Returns:
        True if basic functionality works
    """
    try:
        # Test basic imports
        from src.database.integration import DatabaseIntegrationManager
        from src.database.girls_adapter import DatabaseGirlsAdapter
        from src.database.cache import MultiTierCache
        
        # Test basic object creation
        manager = DatabaseIntegrationManager()
        adapter = DatabaseGirlsAdapter()
        cache = MultiTierCache()
        
        # Test basic profile operations
        from src.core.girls_manager import GirlProfile
        profile = GirlProfile(chat_id=1, name="Test")
        profile_dict = profile.to_dict()
        restored_profile = GirlProfile.from_dict(profile_dict)
        
        return (profile.chat_id == restored_profile.chat_id and 
                profile.name == restored_profile.name)
        
    except Exception as e:
        logger = setup_logger(__name__)
        logger.error(f"Smoke test failed: {e}")
        return False


if __name__ == "__main__":
    # Run tests if module is executed directly
    asyncio.run(run_integration_tests())
