"""
Configuration Manager - Dynamic Per-Bot Configuration Management

Система для управления динамическими конфигурациями bot processes.
Поддерживает hot-reload настроек, per-bot конфигурации,
validation правил и configuration versioning.

Функции:
- Dynamic configuration loading и hot-reload
- Per-bot configuration isolation
- Configuration validation и schema enforcement  
- Version control для configuration changes
- Configuration inheritance и templating
- Configuration change notifications
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Any, List, Callable, Union
import aiofiles
import aiofiles.os
from src.config.config import Config, TelegramConfig, DatabaseConfig


class ConfigurationScope(Enum):
    """Область применения конфигурации"""
    GLOBAL = "global"          # Глобальные настройки для всех ботов
    BOT_TYPE = "bot_type"      # Настройки для типа бота
    BOT_INSTANCE = "instance"  # Настройки для конкретного бота
    RUNTIME = "runtime"        # Временные настройки времени выполнения


class ConfigurationSource(Enum):
    """Источник конфигурации"""
    FILE = "file"              # Конфигурация из файла
    DATABASE = "database"      # Конфигурация из базы данных
    ENVIRONMENT = "environment" # Переменные окружения
    API = "api"               # Настройки через API
    RUNTIME = "runtime"       # Настройки времени выполнения


@dataclass
class ConfigurationChange:
    """Изменение конфигурации"""
    change_id: str
    bot_id: str
    scope: ConfigurationScope
    source: ConfigurationSource
    key_path: str
    old_value: Any
    new_value: Any
    timestamp: float
    user_id: Optional[str] = None
    reason: str = ""
    applied: bool = False
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass  
class BotConfiguration:
    """Полная конфигурация бота"""
    bot_id: str
    bot_type: str
    global_config: Dict[str, Any] = field(default_factory=dict)
    type_config: Dict[str, Any] = field(default_factory=dict)
    instance_config: Dict[str, Any] = field(default_factory=dict)
    runtime_config: Dict[str, Any] = field(default_factory=dict)
    
    # Метаданные
    version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_reload: float = field(default_factory=time.time)
    
    def get_merged_config(self) -> Dict[str, Any]:
        """Получение объединенной конфигурации с приоритетами"""
        merged = {}
        
        # Порядок приоритета: global -> type -> instance -> runtime
        merged.update(self.global_config)
        merged.update(self.type_config)
        merged.update(self.instance_config)
        merged.update(self.runtime_config)
        
        return merged
    
    def get_config_value(self, key_path: str, default: Any = None) -> Any:
        """Получение значения конфигурации по пути"""
        merged = self.get_merged_config()
        
        # Поддержка dot notation: "telegram.api_id"
        keys = key_path.split('.')
        value = merged
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set_config_value(self, key_path: str, value: Any, scope: ConfigurationScope = ConfigurationScope.RUNTIME):
        """Установка значения конфигурации"""
        keys = key_path.split('.')
        
        # Выбор target configuration
        if scope == ConfigurationScope.GLOBAL:
            target = self.global_config
        elif scope == ConfigurationScope.BOT_TYPE:
            target = self.type_config
        elif scope == ConfigurationScope.BOT_INSTANCE:
            target = self.instance_config
        else:
            target = self.runtime_config
        
        # Создание nested structure если нужно
        current = target
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
        self.updated_at = time.time()


class ConfigurationValidator:
    """Валидатор конфигураций"""
    
    def __init__(self):
        self.schemas: Dict[str, Dict] = {}
        self.custom_validators: Dict[str, Callable] = {}
        
        # Базовые схемы
        self._setup_base_schemas()
    
    def _setup_base_schemas(self):
        """Настройка базовых схем валидации"""
        self.schemas['telegram'] = {
            'api_id': {'type': 'int', 'required': True, 'min': 1},
            'api_hash': {'type': 'str', 'required': True, 'min_length': 10},
            'phone': {'type': 'str', 'required': True, 'pattern': r'^\+\d{10,15}$'},
            'session_name': {'type': 'str', 'required': False, 'default': 'bot_session'}
        }
        
        self.schemas['database'] = {
            'host': {'type': 'str', 'required': True},
            'port': {'type': 'int', 'required': True, 'min': 1, 'max': 65535},
            'database': {'type': 'str', 'required': True},
            'username': {'type': 'str', 'required': True},
            'password': {'type': 'str', 'required': True, 'min_length': 8}
        }
        
        self.schemas['bot_settings'] = {
            'max_conversations': {'type': 'int', 'min': 1, 'max': 100, 'default': 10},
            'response_delay': {'type': 'float', 'min': 0.1, 'max': 30.0, 'default': 2.0},
            'conversation_timeout': {'type': 'int', 'min': 300, 'max': 86400, 'default': 3600}
        }
        
        self.schemas['resources'] = {
            'max_memory_mb': {'type': 'int', 'min': 100, 'max': 8192, 'default': 512},
            'max_cpu_percent': {'type': 'float', 'min': 10.0, 'max': 100.0, 'default': 50.0},
            'max_connections': {'type': 'int', 'min': 1, 'max': 1000, 'default': 50}
        }
    
    def register_schema(self, name: str, schema: Dict):
        """Регистрация новой схемы"""
        self.schemas[name] = schema
    
    def register_validator(self, name: str, validator: Callable):
        """Регистрация custom validator"""
        self.custom_validators[name] = validator
    
    def validate_config(self, config: Dict[str, Any], schema_name: str = None) -> Dict[str, List[str]]:
        """
        Валидация конфигурации
        
        Returns:
            Dict[str, List[str]]: Ошибки валидации по ключам
        """
        errors = {}
        
        if schema_name and schema_name in self.schemas:
            schema = self.schemas[schema_name]
            errors.update(self._validate_against_schema(config, schema, schema_name))
        else:
            # Валидация против всех известных схем
            for section_name, section_config in config.items():
                if section_name in self.schemas:
                    section_errors = self._validate_against_schema(
                        section_config, self.schemas[section_name], section_name
                    )
                    if section_errors:
                        errors[section_name] = section_errors
        
        return errors
    
    def _validate_against_schema(self, config: Dict, schema: Dict, prefix: str = "") -> Dict[str, List[str]]:
        """Валидация против конкретной схемы"""
        errors = {}
        
        # Проверка required полей
        for field_name, field_schema in schema.items():
            field_path = f"{prefix}.{field_name}" if prefix else field_name
            
            if field_schema.get('required', False) and field_name not in config:
                errors[field_path] = [f"Required field '{field_name}' is missing"]
                continue
            
            if field_name not in config:
                continue
            
            value = config[field_name]
            field_errors = self._validate_field(value, field_schema, field_name)
            
            if field_errors:
                errors[field_path] = field_errors
        
        return errors
    
    def _validate_field(self, value: Any, schema: Dict, field_name: str) -> List[str]:
        """Валидация отдельного поля"""
        errors = []
        
        # Type validation
        expected_type = schema.get('type')
        if expected_type:
            if expected_type == 'int' and not isinstance(value, int):
                errors.append(f"Expected integer, got {type(value).__name__}")
            elif expected_type == 'float' and not isinstance(value, (int, float)):
                errors.append(f"Expected float, got {type(value).__name__}")
            elif expected_type == 'str' and not isinstance(value, str):
                errors.append(f"Expected string, got {type(value).__name__}")
        
        # Range validation
        if isinstance(value, (int, float)):
            min_val = schema.get('min')
            max_val = schema.get('max')
            
            if min_val is not None and value < min_val:
                errors.append(f"Value {value} is less than minimum {min_val}")
            
            if max_val is not None and value > max_val:
                errors.append(f"Value {value} is greater than maximum {max_val}")
        
        # String validation
        if isinstance(value, str):
            min_length = schema.get('min_length')
            max_length = schema.get('max_length')
            pattern = schema.get('pattern')
            
            if min_length is not None and len(value) < min_length:
                errors.append(f"String length {len(value)} is less than minimum {min_length}")
            
            if max_length is not None and len(value) > max_length:
                errors.append(f"String length {len(value)} is greater than maximum {max_length}")
            
            if pattern is not None:
                import re
                if not re.match(pattern, value):
                    errors.append(f"String does not match pattern {pattern}")
        
        # Custom validation
        custom_validator = schema.get('validator')
        if custom_validator and custom_validator in self.custom_validators:
            try:
                custom_result = self.custom_validators[custom_validator](value)
                if custom_result is not True:
                    errors.append(str(custom_result))
            except Exception as e:
                errors.append(f"Custom validation error: {e}")
        
        return errors


class ConfigurationManager:
    """
    Configuration Manager - система управления конфигурациями для ProcessSupervisor
    
    Функции:
    - Dynamic configuration loading и hot-reload
    - Per-bot configuration management
    - Configuration validation и consistency checks
    - Change tracking и audit trail
    - Configuration templates и inheritance
    """
    
    def __init__(self, config_dir: Path, base_config: Optional[Config] = None):
        self.config_dir = Path(config_dir)
        self.base_config = base_config or Config()
        self.logger = logging.getLogger(__name__)
        
        # Configuration storage
        self.bot_configurations: Dict[str, BotConfiguration] = {}
        self.configuration_templates: Dict[str, Dict] = {}
        self.change_history: List[ConfigurationChange] = []
        
        # Validation
        self.validator = ConfigurationValidator()
        
        # Change notifications
        self.change_listeners: List[Callable] = []
        
        # Состояние системы
        self.is_monitoring = False
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Кеширование
        self.config_cache: Dict[str, Any] = {}
        self.cache_ttl = 300  # 5 минут
        self.cache_timestamps: Dict[str, float] = {}
    
    async def start(self):
        """Запуск Configuration Manager"""
        try:
            self.logger.info("Starting Configuration Manager")
            
            # Создание директорий
            await self._ensure_directories()
            
            # Загрузка конфигураций
            await self._load_configurations()
            
            # Загрузка шаблонов
            await self._load_templates()
            
            # Запуск мониторинга
            self.is_monitoring = True
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            self.logger.info("Configuration Manager started successfully")
            
        except Exception as e:
            self.logger.error(f"Error starting Configuration Manager: {e}")
            raise
    
    async def stop(self):
        """Остановка Configuration Manager"""
        try:
            self.logger.info("Stopping Configuration Manager")
            
            self.is_monitoring = False
            
            if self.monitoring_task:
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    pass
            
            # Сохранение состояния
            await self._save_all_configurations()
            
            self.logger.info("Configuration Manager stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Configuration Manager: {e}")
    
    async def create_bot_configuration(self, bot_id: str, bot_type: str, initial_config: Optional[Dict] = None) -> BotConfiguration:
        """Создание конфигурации для нового бота"""
        try:
            if bot_id in self.bot_configurations:
                return self.bot_configurations[bot_id]
            
            # Создание конфигурации
            config = BotConfiguration(
                bot_id=bot_id,
                bot_type=bot_type
            )
            
            # Применение глобальных настроек
            config.global_config = await self._get_global_config()
            
            # Применение настроек типа
            config.type_config = await self._get_type_config(bot_type)
            
            # Применение начальных настроек
            if initial_config:
                config.instance_config = initial_config.copy()
            
            # Валидация
            validation_errors = self._validate_bot_configuration(config)
            if validation_errors:
                raise ValueError(f"Configuration validation failed: {validation_errors}")
            
            # Сохранение
            self.bot_configurations[bot_id] = config
            await self._save_bot_configuration(bot_id)
            
            # Уведомление об изменении
            await self._notify_configuration_change(bot_id, "created", {})
            
            self.logger.info(f"Created configuration for bot {bot_id} (type: {bot_type})")
            return config
            
        except Exception as e:
            self.logger.error(f"Error creating configuration for bot {bot_id}: {e}")
            raise
    
    async def get_bot_configuration(self, bot_id: str) -> Optional[BotConfiguration]:
        """Получение конфигурации бота"""
        if bot_id in self.bot_configurations:
            return self.bot_configurations[bot_id]
        
        # Попытка загрузки из файла
        try:
            config_file = self.config_dir / "bots" / f"{bot_id}.json"
            if await aiofiles.os.path.exists(config_file):
                async with aiofiles.open(config_file, 'r') as f:
                    data = json.loads(await f.read())
                
                config = BotConfiguration(**data)
                self.bot_configurations[bot_id] = config
                return config
        except Exception as e:
            self.logger.error(f"Error loading configuration for bot {bot_id}: {e}")
        
        return None
    
    async def update_bot_configuration(self, bot_id: str, key_path: str, value: Any, 
                                     scope: ConfigurationScope = ConfigurationScope.RUNTIME,
                                     source: ConfigurationSource = ConfigurationSource.API,
                                     user_id: Optional[str] = None, reason: str = "") -> bool:
        """Обновление конфигурации бота"""
        try:
            config = await self.get_bot_configuration(bot_id)
            if not config:
                raise ValueError(f"Configuration for bot {bot_id} not found")
            
            # Сохранение старого значения
            old_value = config.get_config_value(key_path)
            
            # Установка нового значения
            config.set_config_value(key_path, value, scope)
            
            # Валидация
            validation_errors = self._validate_bot_configuration(config)
            if validation_errors:
                # Откат изменения
                config.set_config_value(key_path, old_value, scope)
                raise ValueError(f"Configuration validation failed: {validation_errors}")
            
            # Запись изменения в историю
            change = ConfigurationChange(
                change_id=str(uuid.uuid4()),
                bot_id=bot_id,
                scope=scope,
                source=source,
                key_path=key_path,
                old_value=old_value,
                new_value=value,
                timestamp=time.time(),
                user_id=user_id,
                reason=reason,
                applied=True
            )
            
            self.change_history.append(change)
            
            # Сохранение конфигурации
            await self._save_bot_configuration(bot_id)
            
            # Уведомление об изменении
            await self._notify_configuration_change(bot_id, "updated", {
                'key_path': key_path,
                'old_value': old_value,
                'new_value': value,
                'scope': scope.value
            })
            
            # Очистка кеша
            self._clear_bot_cache(bot_id)
            
            self.logger.info(f"Updated configuration for bot {bot_id}: {key_path} = {value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating configuration for bot {bot_id}: {e}")
            return False
    
    async def reload_bot_configuration(self, bot_id: str) -> bool:
        """Перезагрузка конфигурации бота из файла"""
        try:
            # Удаление из памяти
            if bot_id in self.bot_configurations:
                del self.bot_configurations[bot_id]
            
            # Очистка кеша
            self._clear_bot_cache(bot_id)
            
            # Загрузка заново
            config = await self.get_bot_configuration(bot_id)
            
            if config:
                config.last_reload = time.time()
                await self._notify_configuration_change(bot_id, "reloaded", {})
                self.logger.info(f"Reloaded configuration for bot {bot_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error reloading configuration for bot {bot_id}: {e}")
            return False
    
    def get_merged_config(self, bot_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Получение объединенной конфигурации с кешированием"""
        cache_key = f"merged_{bot_id}"
        
        # Проверка кеша
        if use_cache and cache_key in self.config_cache:
            cache_time = self.cache_timestamps.get(cache_key, 0)
            if time.time() - cache_time < self.cache_ttl:
                return self.config_cache[cache_key]
        
        # Получение конфигурации
        if bot_id not in self.bot_configurations:
            return None
        
        config = self.bot_configurations[bot_id]
        merged = config.get_merged_config()
        
        # Кеширование
        if use_cache:
            self.config_cache[cache_key] = merged
            self.cache_timestamps[cache_key] = time.time()
        
        return merged
    
    async def _ensure_directories(self):
        """Создание необходимых директорий"""
        directories = [
            self.config_dir,
            self.config_dir / "bots",
            self.config_dir / "templates",
            self.config_dir / "global",
            self.config_dir / "types",
            self.config_dir / "backups"
        ]
        
        for directory in directories:
            await aiofiles.os.makedirs(directory, exist_ok=True)
    
    async def _load_configurations(self):
        """Загрузка всех конфигураций"""
        bots_dir = self.config_dir / "bots"
        
        if await aiofiles.os.path.exists(bots_dir):
            for file_path in bots_dir.iterdir():
                if file_path.suffix == '.json':
                    bot_id = file_path.stem
                    try:
                        await self.get_bot_configuration(bot_id)
                    except Exception as e:
                        self.logger.error(f"Error loading configuration for {bot_id}: {e}")
    
    async def _load_templates(self):
        """Загрузка шаблонов конфигураций"""
        templates_dir = self.config_dir / "templates"
        
        if await aiofiles.os.path.exists(templates_dir):
            for file_path in templates_dir.iterdir():
                if file_path.suffix == '.json':
                    template_name = file_path.stem
                    try:
                        async with aiofiles.open(file_path, 'r') as f:
                            template_data = json.loads(await f.read())
                        
                        self.configuration_templates[template_name] = template_data
                        
                    except Exception as e:
                        self.logger.error(f"Error loading template {template_name}: {e}")
    
    async def _get_global_config(self) -> Dict[str, Any]:
        """Получение глобальной конфигурации"""
        global_file = self.config_dir / "global" / "config.json"
        
        if await aiofiles.os.path.exists(global_file):
            try:
                async with aiofiles.open(global_file, 'r') as f:
                    return json.loads(await f.read())
            except Exception as e:
                self.logger.error(f"Error loading global config: {e}")
        
        return {}
    
    async def _get_type_config(self, bot_type: str) -> Dict[str, Any]:
        """Получение конфигурации типа бота"""
        type_file = self.config_dir / "types" / f"{bot_type}.json"
        
        if await aiofiles.os.path.exists(type_file):
            try:
                async with aiofiles.open(type_file, 'r') as f:
                    return json.loads(await f.read())
            except Exception as e:
                self.logger.error(f"Error loading type config for {bot_type}: {e}")
        
        return {}
    
    def _validate_bot_configuration(self, config: BotConfiguration) -> Dict[str, List[str]]:
        """Валидация конфигурации бота"""
        merged = config.get_merged_config()
        return self.validator.validate_config(merged)
    
    async def _save_bot_configuration(self, bot_id: str):
        """Сохранение конфигурации бота"""
        if bot_id not in self.bot_configurations:
            return
        
        config = self.bot_configurations[bot_id]
        config_file = self.config_dir / "bots" / f"{bot_id}.json"
        
        try:
            # Создание резервной копии
            if await aiofiles.os.path.exists(config_file):
                backup_file = self.config_dir / "backups" / f"{bot_id}_{int(time.time())}.json"
                async with aiofiles.open(config_file, 'r') as src, aiofiles.open(backup_file, 'w') as dst:
                    await dst.write(await src.read())
            
            # Сохранение конфигурации
            config_data = asdict(config)
            async with aiofiles.open(config_file, 'w') as f:
                await f.write(json.dumps(config_data, indent=2))
                
        except Exception as e:
            self.logger.error(f"Error saving configuration for bot {bot_id}: {e}")
    
    async def _save_all_configurations(self):
        """Сохранение всех конфигураций"""
        for bot_id in self.bot_configurations:
            await self._save_bot_configuration(bot_id)
    
    async def _notify_configuration_change(self, bot_id: str, change_type: str, details: Dict):
        """Уведомление об изменении конфигурации"""
        for listener in self.change_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(bot_id, change_type, details)
                else:
                    listener(bot_id, change_type, details)
            except Exception as e:
                self.logger.error(f"Error in configuration change listener: {e}")
    
    def _clear_bot_cache(self, bot_id: str):
        """Очистка кеша для бота"""
        keys_to_remove = [key for key in self.config_cache.keys() if bot_id in key]
        for key in keys_to_remove:
            del self.config_cache[key]
            if key in self.cache_timestamps:
                del self.cache_timestamps[key]
    
    async def _monitoring_loop(self):
        """Цикл мониторинга изменений файлов конфигурации"""
        file_timestamps = {}
        
        while self.is_monitoring:
            try:
                # Проверка изменений в файлах
                for config_dir in [self.config_dir / "bots", self.config_dir / "global", self.config_dir / "types"]:
                    if await aiofiles.os.path.exists(config_dir):
                        for file_path in config_dir.iterdir():
                            if file_path.suffix == '.json':
                                stat = file_path.stat()
                                current_mtime = stat.st_mtime
                                
                                if file_path not in file_timestamps:
                                    file_timestamps[file_path] = current_mtime
                                elif file_timestamps[file_path] != current_mtime:
                                    # Файл изменился
                                    file_timestamps[file_path] = current_mtime
                                    await self._handle_file_change(file_path)
                
                await asyncio.sleep(5)  # Проверка каждые 5 секунд
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)
    
    async def _handle_file_change(self, file_path: Path):
        """Обработка изменения файла конфигурации"""
        try:
            if file_path.parent.name == "bots":
                # Изменение конфигурации бота
                bot_id = file_path.stem
                await self.reload_bot_configuration(bot_id)
            elif file_path.parent.name in ["global", "types"]:
                # Изменение глобальной конфигурации или типа
                # Перезагрузка всех конфигураций
                for bot_id in list(self.bot_configurations.keys()):
                    await self.reload_bot_configuration(bot_id)
                    
        except Exception as e:
            self.logger.error(f"Error handling file change {file_path}: {e}")
    
    def add_change_listener(self, listener: Callable):
        """Добавление слушателя изменений конфигурации"""
        self.change_listeners.append(listener)
    
    def remove_change_listener(self, listener: Callable):
        """Удаление слушателя изменений конфигурации"""
        if listener in self.change_listeners:
            self.change_listeners.remove(listener)
    
    def get_change_history(self, bot_id: Optional[str] = None, limit: int = 100) -> List[ConfigurationChange]:
        """Получение истории изменений"""
        history = self.change_history
        
        if bot_id:
            history = [change for change in history if change.bot_id == bot_id]
        
        # Сортировка по времени (новые первыми)
        history.sort(key=lambda x: x.timestamp, reverse=True)
        
        return history[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики Configuration Manager"""
        return {
            'total_bots': len(self.bot_configurations),
            'total_templates': len(self.configuration_templates),
            'total_changes': len(self.change_history),
            'cache_size': len(self.config_cache),
            'is_monitoring': self.is_monitoring,
            'bot_types': list(set(config.bot_type for config in self.bot_configurations.values())),
            'recent_changes': len([
                change for change in self.change_history 
                if time.time() - change.timestamp < 3600  # Последний час
            ])
        }
