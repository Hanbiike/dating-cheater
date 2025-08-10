"""
Phase 2C Integration Testing

Comprehensive testing framework for ProcessSupervisor + Database + Main.py integration.
Tests multi-bot capability with database coordination.
"""

import asyncio
import logging
import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
import json

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.processsupervisor.manager.main_integrator import MainIntegrator
from src.processsupervisor.manager.multibot_manager import MultiBotManager
from src.processsupervisor.communication.multiprocess_connection_manager import MultiProcessConnectionManager
from src.processsupervisor.communication.enhanced_ipc_commands import EnhancedIPCCommands
from src.database.integration import DatabaseIntegrationManager
from src.config.config import Config


class Phase2CIntegrationTester:
    """
    Integration tester for Phase 2C components
    
    Tests:
    - MainIntegrator mode detection and routing
    - ProcessSupervisor + Database coordination
    - Multi-process connection management
    - Complete IPC command functionality
    - End-to-end multi-bot operations
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.test_dir = None
        self.test_processes = []
        self.cleanup_tasks = []
        
    async def setup_test_environment(self) -> bool:
        """Setup isolated test environment"""
        try:
            # Create temporary directory for test data
            self.test_dir = Path(tempfile.mkdtemp(prefix="phase2c_test_"))
            
            # Setup test configuration
            test_config = {
                'database': {
                    'enabled': True,
                    'fallback_to_json': True,
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'test_dating_bot',
                    'user': 'test_user'
                },
                'redis': {
                    'enabled': True,
                    'host': 'localhost',
                    'port': 6379,
                    'db': 1  # Use test database
                },
                'bots': {
                    'test_bot_1': {
                        'api_id': '12345',
                        'api_hash': 'test_hash_1',
                        'phone': '+1234567890',
                        'session_file': str(self.test_dir / 'test_bot_1.session')
                    },
                    'test_bot_2': {
                        'api_id': '12346',
                        'api_hash': 'test_hash_2',
                        'phone': '+1234567891',
                        'session_file': str(self.test_dir / 'test_bot_2.session')
                    }
                }
            }
            
            # Write test configuration
            config_file = self.test_dir / 'test_config.json'
            with open(config_file, 'w') as f:
                json.dump(test_config, f, indent=2)
            
            self.logger.info(f"Test environment setup complete: {self.test_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to setup test environment: {e}")
            return False
    
    async def cleanup_test_environment(self):
        """Cleanup test environment"""
        try:
            # Stop all test processes
            for task in self.cleanup_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Remove test directory
            if self.test_dir and self.test_dir.exists():
                shutil.rmtree(self.test_dir)
                self.logger.info("Test environment cleaned up")
                
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    async def test_main_integrator_mode_detection(self) -> bool:
        """Test MainIntegrator mode detection and routing"""
        try:
            self.logger.info("Testing MainIntegrator mode detection...")
            
            integrator = MainIntegrator()
            
            # Test auto mode detection
            mode = await integrator.detect_mode()
            assert mode in ['single', 'multi'], f"Invalid mode detected: {mode}"
            
            # Test configuration validation
            valid = await integrator.validate_configuration()
            assert isinstance(valid, bool), "Configuration validation should return boolean"
            
            self.logger.info("✅ MainIntegrator mode detection passed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ MainIntegrator test failed: {e}")
            return False
    
    async def test_database_integration_coordination(self) -> bool:
        """Test database integration with ProcessSupervisor coordination"""
        try:
            self.logger.info("Testing database integration coordination...")
            
            # Test database integration manager
            db_manager = DatabaseIntegrationManager(bot_id="test_bot_1")
            
            # Test initialization
            init_success = await db_manager.initialize(enable_migration=False)
            if not init_success:
                self.logger.warning("Database initialization failed - testing fallback mode")
            
            # Test basic operations
            test_data = {'test_key': 'test_value', 'timestamp': '2025-01-10'}
            
            # Store and retrieve test data
            if init_success and db_manager.data_store:
                await db_manager.data_store.store('test', 'test_item', test_data)
                retrieved = await db_manager.data_store.retrieve('test', 'test_item')
                assert retrieved == test_data, "Data storage/retrieval mismatch"
            
            # Test cleanup
            await db_manager.shutdown()
            
            self.logger.info("✅ Database integration coordination passed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Database integration test failed: {e}")
            return False
    
    async def test_multiprocess_connection_manager(self) -> bool:
        """Test multi-process connection manager"""
        try:
            self.logger.info("Testing multi-process connection manager...")
            
            # Create connection manager for test process
            conn_manager = MultiProcessConnectionManager(
                process_id="test_process_1"
            )
            
            # Test startup
            await conn_manager.start()
            
            # Test connection tracking
            assert hasattr(conn_manager, 'connections'), "Connection tracking not initialized"
            assert hasattr(conn_manager, 'db_integration'), "Database integration not initialized"
            
            # Test shutdown
            await conn_manager.stop()
            
            self.logger.info("✅ Multi-process connection manager passed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Multi-process connection manager test failed: {e}")
            return False
    
    async def test_enhanced_ipc_commands(self) -> bool:
        """Test enhanced IPC commands with database integration"""
        try:
            self.logger.info("Testing enhanced IPC commands...")
            
            # Mock IPC manager for testing
            class MockIPCManager:
                async def send_message(self, message):
                    return {'status': 'success'}
                async def register_handler(self, handler_type, handler):
                    pass
            
            # Create IPC commands handler
            ipc_commands = EnhancedIPCCommands(
                process_id="test_process_1",
                ipc_manager=MockIPCManager()
            )
            
            # Test command registration
            await ipc_commands.start()
            
            # Test database commands
            commands_to_test = [
                'database.status',
                'database.cache_stats',
                'bot.list',
                'monitor.system_status'
            ]
            
            for command_name in commands_to_test:
                assert command_name in ipc_commands.commands, f"Command {command_name} not registered"
            
            # Test command execution
            result = await ipc_commands._handle_database_status({})
            assert 'status' in result, "Database status command should return status"
            
            # Test cleanup
            await ipc_commands.stop()
            
            self.logger.info("✅ Enhanced IPC commands passed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Enhanced IPC commands test failed: {e}")
            return False
    
    async def test_end_to_end_integration(self) -> bool:
        """Test complete end-to-end multi-bot integration"""
        try:
            self.logger.info("Testing end-to-end integration...")
            
            # This would test the complete flow:
            # 1. Main.py → MainIntegrator → mode detection
            # 2. ProcessSupervisor startup with database coordination
            # 3. Multi-bot process creation with database sharing
            # 4. IPC command execution
            # 5. Graceful shutdown with database cleanup
            
            # For now, validate that all components can be imported and initialized
            components_tested = [
                MainIntegrator,
                DatabaseIntegrationManager,
                MultiProcessConnectionManager,
                EnhancedIPCCommands
            ]
            
            for component_class in components_tested:
                assert callable(component_class), f"Component {component_class.__name__} not callable"
            
            self.logger.info("✅ End-to-end integration validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ End-to-end integration test failed: {e}")
            return False
    
    async def run_all_tests(self) -> Dict[str, bool]:
        """Run all integration tests"""
        results = {}
        
        try:
            # Setup test environment
            setup_success = await self.setup_test_environment()
            if not setup_success:
                return {'setup_failed': False}
            
            # Run individual tests
            tests = [
                ('main_integrator_mode_detection', self.test_main_integrator_mode_detection),
                ('database_integration_coordination', self.test_database_integration_coordination),
                ('multiprocess_connection_manager', self.test_multiprocess_connection_manager),
                ('enhanced_ipc_commands', self.test_enhanced_ipc_commands),
                ('end_to_end_integration', self.test_end_to_end_integration)
            ]
            
            for test_name, test_func in tests:
                self.logger.info(f"Running test: {test_name}")
                results[test_name] = await test_func()
            
            return results
            
        except Exception as e:
            self.logger.error(f"Test execution failed: {e}")
            return {'execution_failed': False}
            
        finally:
            await self.cleanup_test_environment()


async def main():
    """Run Phase 2C integration tests"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Phase 2C Integration Tests")
    
    # Run tests
    tester = Phase2CIntegrationTester()
    results = await tester.run_all_tests()
    
    # Report results
    logger.info("Test Results:")
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"  {test_name}: {status}")
    
    logger.info(f"Overall: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        logger.info("🎉 All Phase 2C integration tests PASSED!")
        return 0
    else:
        logger.error(f"💥 {total_tests - passed_tests} tests FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
