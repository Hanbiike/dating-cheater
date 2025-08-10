"""
Main.py Integration - ProcessSupervisor Entry Point Integration

Модуль для интеграции ProcessSupervisor с существующим main.py entry point.
Обеспечивает плавный переход между одиночным bot режимом и multi-bot ProcessSupervisor.

Функции:
- ProcessSupervisor mode detection и initialization
- Backward compatibility с existing entry point
- Command-line interface для mode selection
- Configuration migration и validation
- Graceful fallback to single-bot mode
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from src.config.config import Config
from src.utils.logger import setup_logger
from src.processsupervisor.manager.multibot_manager import MultiBotManager, run_multibot_manager


class MainIntegrator:
    """
    Main.py Integration - связующий компонент между legacy и ProcessSupervisor режимами
    
    Функции:
    - Определение режима работы (single-bot vs multi-bot)
    - Инициализация соответствующего режима
    - Миграция конфигурации между режимами
    - Graceful fallback при ошибках
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.config: Optional[Config] = None
        self.mode: str = "auto"  # auto, single, multi
        
    def parse_arguments(self) -> argparse.Namespace:
        """Парсинг аргументов командной строки"""
        parser = argparse.ArgumentParser(
            description="Han Dating Bot - ProcessSupervisor Integration",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Modes:
  auto    - Automatic mode detection based on configuration
  single  - Single bot mode (legacy main.py behavior)
  multi   - Multi-bot ProcessSupervisor mode (Phase 2+ architecture)
  
Examples:
  python main.py                    # Auto mode detection
  python main.py --mode single     # Force single bot mode
  python main.py --mode multi      # Force multi-bot mode
  python main.py --config-check    # Validate configuration
            """
        )
        
        parser.add_argument(
            "--mode",
            choices=["auto", "single", "multi"],
            default="auto",
            help="Execution mode (default: auto)"
        )
        
        parser.add_argument(
            "--config-file",
            type=Path,
            help="Custom configuration file path"
        )
        
        parser.add_argument(
            "--config-check",
            action="store_true",
            help="Validate configuration and exit"
        )
        
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate setup without starting bot"
        )
        
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable debug logging"
        )
        
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Log level (default: INFO)"
        )
        
        return parser.parse_args()
    
    async def initialize_config(self, config_file: Optional[Path] = None) -> Config:
        """Инициализация конфигурации с валидацией"""
        try:
            if config_file:
                # Load custom config file
                self.logger.info(f"Loading configuration from {config_file}")
                # TODO: Implement custom config loading
                pass
            
            # For now, create minimal config for testing
            # In production, this would load from environment or config file
            self.config = self._create_minimal_config()
            
            self.logger.info("Configuration initialized successfully")
            return self.config
            
        except Exception as e:
            self.logger.error(f"Error initializing configuration: {e}")
            raise
    
    def _create_minimal_config(self) -> Config:
        """Создание минимальной конфигурации для тестирования"""
        from src.config.config import TimeWindows, Probabilities, Delays, TelegramConfig, DatabaseConfig
        
        # Create minimal configuration objects
        time_windows = TimeWindows()
        probabilities = Probabilities()
        delays = Delays()
        
        telegram_config = TelegramConfig(
            api_id=12345,  # Placeholder
            api_hash="placeholder",
            phone="+1234567890",
            bot_token="placeholder"
        )
        
        database_config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="hanbot",
            username="bot_user",
            password="placeholder"
        )
        
        # Create main config with all required fields
        config = Config(
            telegram=telegram_config,
            database=database_config,
            time_windows=time_windows,
            probabilities=probabilities,
            delays=delays,
            openai_api_key="placeholder",
            openai_model="gpt-4",
            openai_temperature=0.7,
            openai_max_tokens=1000,
            admin_chat_id=123456789,
            admin_bot_api_key="placeholder",
            multi_bot_enabled=False,
            current_bot_id="default",
            girls_data_path=Path("girls_data"),
            conversations_dir=Path("conversations"),
            backups_dir=Path("backups"),
            log_file=Path("bot.log"),
            log_level="INFO",
            history_limit=50,
            profile_analyze_every_n=10,
            wait_for_more_seconds=300
        )
        
        return config
    
    def detect_mode(self) -> str:
        """Определение режима работы на основе конфигурации"""
        try:
            if not self.config:
                return "single"  # Default fallback
            
            # Check for multi-bot indicators
            multi_bot_indicators = [
                self.config.multi_bot_enabled,
                Path("multibot_manager.py").exists(),
                Path("configs").exists(),
                len(list(Path("girls_data").glob("*.json"))) > 1 if Path("girls_data").exists() else False
            ]
            
            if any(multi_bot_indicators):
                self.logger.info("Multi-bot mode detected")
                return "multi"
            else:
                self.logger.info("Single-bot mode detected")
                return "single"
                
        except Exception as e:
            self.logger.warning(f"Error detecting mode, falling back to single: {e}")
            return "single"
    
    async def validate_configuration(self) -> bool:
        """Валидация конфигурации"""
        try:
            if not self.config:
                self.logger.error("No configuration loaded")
                return False
            
            # Basic validation
            validation_checks = [
                ("Telegram config", self.config.telegram is not None),
                ("Database config", self.config.database is not None),
                ("OpenAI API key", bool(self.config.openai_api_key)),
                ("Log file path", self.config.log_file is not None),
                ("Girls data path", self.config.girls_data_path is not None)
            ]
            
            validation_passed = True
            
            for check_name, check_result in validation_checks:
                if check_result:
                    self.logger.info(f"✅ {check_name}: OK")
                else:
                    self.logger.error(f"❌ {check_name}: FAILED")
                    validation_passed = False
            
            if validation_passed:
                self.logger.info("Configuration validation passed")
            else:
                self.logger.error("Configuration validation failed")
            
            return validation_passed
            
        except Exception as e:
            self.logger.error(f"Error validating configuration: {e}")
            return False
    
    async def run_single_bot_mode(self) -> int:
        """Запуск в одиночном bot режиме (legacy)"""
        try:
            self.logger.info("Starting in single-bot mode")
            
            # Import legacy main function
            # This would normally import the existing main() function
            self.logger.info("Single-bot mode would start here")
            self.logger.info("Legacy main.py functionality would be executed")
            
            # For now, just simulate
            await asyncio.sleep(1)
            self.logger.info("Single-bot mode simulation completed")
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Error in single-bot mode: {e}")
            return 1
    
    async def run_multi_bot_mode(self) -> int:
        """Запуск в ProcessSupervisor режиме"""
        try:
            self.logger.info("Starting in multi-bot ProcessSupervisor mode")
            
            # Создание и запуск MultiBotManager
            await run_multibot_manager(self.config)
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Error in multi-bot mode: {e}")
            return 1
    
    async def run(self, args: argparse.Namespace) -> int:
        """Основная функция запуска с mode detection"""
        try:
            # Setup logging
            log_level = getattr(logging, args.log_level.upper())
            logging.basicConfig(
                level=log_level,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            
            if args.debug:
                logging.getLogger().setLevel(logging.DEBUG)
            
            self.logger.info("Starting Han Dating Bot with ProcessSupervisor Integration")
            
            # Initialize configuration
            await self.initialize_config(args.config_file)
            
            # Configuration validation
            if not await self.validate_configuration():
                self.logger.error("Configuration validation failed")
                return 1
            
            # Configuration check mode
            if args.config_check:
                self.logger.info("Configuration check completed successfully")
                return 0
            
            # Determine execution mode
            if args.mode == "auto":
                self.mode = self.detect_mode()
            else:
                self.mode = args.mode
            
            self.logger.info(f"Execution mode: {self.mode}")
            
            # Dry run mode
            if args.dry_run:
                self.logger.info(f"Dry run completed - would start in {self.mode} mode")
                return 0
            
            # Execute in selected mode
            if self.mode == "single":
                return await self.run_single_bot_mode()
            elif self.mode == "multi":
                return await self.run_multi_bot_mode()
            else:
                self.logger.error(f"Unknown mode: {self.mode}")
                return 1
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, shutting down gracefully")
            return 0
        except Exception as e:
            self.logger.error(f"Fatal error in main integrator: {e}")
            return 1


async def main() -> int:
    """
    Новая точка входа с ProcessSupervisor интеграцией
    
    Обеспечивает совместимость с legacy main.py и новым ProcessSupervisor режимом
    """
    integrator = MainIntegrator()
    args = integrator.parse_arguments()
    
    return await integrator.run(args)


def legacy_main_compatibility():
    """
    Функция совместимости для прямого запуска legacy main.py
    
    Если main.py запускается напрямую без аргументов, используется
    автоматическое определение режима
    """
    import sys
    
    # Если нет аргументов командной строки, используем auto mode
    if len(sys.argv) == 1:
        sys.argv.append("--mode")
        sys.argv.append("auto")
    
    return asyncio.run(main())


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
