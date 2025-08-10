# Architecture Design: Multi-bot Support

## Высокоуровневая архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    Multi-Bot Manager                    │
├─────────────────────────────────────────────────────────┤
│  Configuration │  Discovery  │  Health Check │  Metrics │
└─────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐   ┌────────▼────────┐   ┌────────▼────────┐
│   Bot Instance │   │   Bot Instance  │   │   Bot Instance  │
│   (bot_id_1)   │   │   (bot_id_2)    │   │   (bot_id_N)    │
├────────────────┤   ├─────────────────┤   ├─────────────────┤
│ • TelegramClient│   │ • TelegramClient│   │ • TelegramClient│
│ • GirlsManager │   │ • GirlsManager  │   │ • GirlsManager  │
│ • ResponseGen  │   │ • ResponseGen   │   │ • ResponseGen   │
│ • AutonomousMan│   │ • AutonomousMan │   │ • AutonomousMan │
└────────────────┘   └─────────────────┘   └─────────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────┐
│                  Shared Infrastructure                  │
├─────────────────────────────────────────────────────────┤
│          Database          │         Message Bus        │
│    ┌─────────────────┐     │    ┌─────────────────┐     │
│    │ bot_configs     │     │    │   Events        │     │
│    │ user_profiles   │     │    │   Commands      │     │
│    │ conversations  │     │    │   Notifications │     │
│    │ metrics_data   │     │    │   Health Checks │     │
│    └─────────────────┘     │    └─────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

## Ключевые компоненты

### 1. Multi-Bot Manager
**Роль**: Центральный orchestrator для управления жизненным циклом ботов

**Ответственности**:
- Bot discovery и registration
- Configuration management
- Health monitoring
- Load balancing
- Graceful startup/shutdown

**Интерфейсы**:
```python
class MultiBotManager:
    async def register_bot(self, bot_config: BotConfig) -> str
    async def remove_bot(self, bot_id: str) -> bool
    async def get_bot_status(self, bot_id: str) -> BotStatus
    async def list_bots(self) -> List[BotInfo]
    async def restart_bot(self, bot_id: str) -> bool
```

### 2. Bot Instance
**Роль**: Изолированный экземпляр бота с полной функциональностью

**Модификации существующих компонентов**:
- **main.py** → **bot_instance.py** - инкапсуляция в класс
- **girls_manager.py** → поддержка bot_id prefix
- **response_generator.py** → изоляция OpenAI клиентов
- **autonomous_manager.py** → раздельные расписания

**Новая структура**:
```python
class BotInstance:
    def __init__(self, bot_id: str, config: BotConfig):
        self.bot_id = bot_id
        self.config = config
        self.client: TelegramClient = None
        self.girls_manager: GirlsManager = None
        self.response_generator: ResponseGenerator = None
        # ... остальные компоненты
```

### 3. Configuration System
**Роль**: Управление конфигурациями множественных ботов

**Структура конфигурации**:
```python
@dataclass
class BotConfig:
    bot_id: str
    name: str
    telegram_api_id: int
    telegram_api_hash: str
    telegram_phone: str
    openai_api_key: str
    admin_chat_id: int
    data_isolation: DataIsolationConfig
    features: FeatureFlags
```

### 4. Database Layer
**Роль**: Централизованное хранение с изоляцией данных по ботам

**Схема таблиц**:
```sql
-- Боты и их конфигурации
CREATE TABLE bots (
    bot_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    config JSONB,
    status VARCHAR(20),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Профили с привязкой к боту
CREATE TABLE user_profiles (
    id SERIAL PRIMARY KEY,
    bot_id VARCHAR(50) REFERENCES bots(bot_id),
    chat_id BIGINT,
    profile_data JSONB,
    created_at TIMESTAMP,
    UNIQUE(bot_id, chat_id)
);

-- Разговоры с привязкой к боту
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    bot_id VARCHAR(50) REFERENCES bots(bot_id),
    chat_id BIGINT,
    message_data JSONB,
    timestamp TIMESTAMP
);
```

### 5. Message Bus (Event System)
**Роль**: Асинхронная коммуникация между компонентами

**События**:
- `BotStarted(bot_id, timestamp)`
- `BotStopped(bot_id, timestamp)`
- `MessageReceived(bot_id, chat_id, message)`
- `HealthCheckFailed(bot_id, error)`

## Patterns и принципы

### 1. Multi-tenancy Pattern
- Изоляция данных через bot_id
- Shared infrastructure с tenant isolation
- Per-tenant configuration

### 2. Actor Model
- Каждый бот как independent actor
- Message passing через event bus
- Fault isolation между актерами

### 3. Factory Pattern
- BotFactory для создания экземпляров
- ConfigurationFactory для настроек
- ComponentFactory для зависимостей

## Migration Strategy

### Phase 1: Infrastructure Setup
1. Создание Multi-Bot Manager
2. Настройка Database layer
3. Реализация Message Bus

### Phase 2: Component Refactoring  
1. Извлечение BotInstance из main.py
2. Модификация managers для multi-tenancy
3. Обновление configuration system

### Phase 3: Data Migration
1. Миграция существующих данных в новую схему
2. Создание default bot из текущей конфигурации
3. Тестирование backward compatibility

### Phase 4: API Layer
1. Реализация REST API для управления ботами
2. Web dashboard для мониторинга
3. Admin panel для конфигурации
