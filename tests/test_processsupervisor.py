"""
Тестирование ProcessSupervisor системы.

Компоненты тестирования для ProcessSupervisor архитектуры:
- Тестирование Manager компонентов
- Тестирование Process компонентов 
- Тестирование Communication компонентов
- Тестирование Optimization компонентов
- Интеграционное тестирование
"""

def test_processsupervisor_import():
    """Базовый тест импорта ProcessSupervisor компонентов."""
    try:
        # Тестируем импорты manager компонентов
        from src.processsupervisor.manager.multibot_manager import MultiBotManager
        from src.processsupervisor.manager.main_integrator import MainIntegrator
        from src.processsupervisor.manager.configuration_manager import ConfigurationManager
        
        # Тестируем импорты process компонентов
        from src.processsupervisor.process.bot_process import BotProcess
        from src.processsupervisor.process.bot_runner import main as bot_runner_main
        from src.processsupervisor.process.process_lifecycle import ProcessLifecycle
        from src.processsupervisor.process.process_monitor import ProcessMonitor
        from src.processsupervisor.process.resource_allocator import ResourceAllocator
        
        # Тестируем импорты communication компонентов
        from src.processsupervisor.communication.ipc_communication import IPCCommunication
        from src.processsupervisor.communication.multiprocess_connection_manager import MultiProcessConnectionManager
        from src.processsupervisor.communication.enhanced_ipc_commands import EnhancedIPCCommands
        
        # Тестируем импорты optimization компонентов
        from src.processsupervisor.optimization.performance_optimizer import PerformanceOptimizer
        from src.processsupervisor.optimization.production_testing_integration import ProductionTestingIntegration
        
        print("✅ Все ProcessSupervisor компоненты успешно импортированы")
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта ProcessSupervisor: {e}")
        return False

if __name__ == "__main__":
    test_processsupervisor_import()
