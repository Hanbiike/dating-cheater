# 🤖 Han Dating Bot - Production Ready

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Telethon](https://img.shields.io/badge/Telegram-Telethon-blue.svg)
![OpenAI](https://img.shields.io/badge/AI-OpenAI-green.svg)
![Docker](https://img.shields.io/badge/Deploy-Docker-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

Продвинутый Telegram бот-ассистент для знакомств с полным набором производственных функций: мониторинг, логирование, обработка ошибок, автоматическое восстановление соединений и containerized deployment.

## ✨ Ключевые особенности

### 🧠 AI & Персонализация
- **Контекстуальная генерация ответов** через OpenAI Responses API
- **Профилирование пользователей** с автоматическим анализом интересов
- **Адаптивные темы разговора** на основе предыдущих диалогов
- **Временная синхронизация** сообщений (time-of-day awareness)

### 🛡️ Production-Ready Architecture
- **Устойчивость к ошибкам** с retry логикой и graceful degradation
- **Мониторинг в реальном времени** с метриками производительности
- **Автоматическое восстановление** соединений при сбоях
- **Rate limiting** для API запросов
- **Валидация данных** на всех уровнях

### 📊 Мониторинг и Аналитика
- **Системные метрики**: uptime, память, производительность
- **API метрики**: успешность запросов, время ответа
- **Пользовательские метрики**: активные чаты, сообщения
- **Health checks** для container orchestration

### 🔒 Безопасность
- **Валидация входных данных** против injection атак
- **Кэширование сущностей** для минимизации API вызовов
- **Логирование безопасности** с фильтрацией sensitive данных
- **Resource limits** в Docker контейнерах

## 🏗️ Архитектура

```
├── core/
│   ├── main.py                     # 🚀 Точка входа с connection management
│   ├── config.py                   # ⚙️ Конфигурация с валидацией
│   ├── exceptions.py               # 🛡️ Кастомные исключения
│   └── validators.py               # ✅ Валидация данных
├── managers/
│   ├── girls_manager.py            # 👥 Управление профилями
│   ├── response_generator.py       # 🧠 AI генерация ответов
│   ├── autonomous_manager.py       # 🤖 Автономные действия
│   └── connection_manager.py       # 🔌 Менеджер соединений
├── monitoring/
│   ├── metrics.py                  # 📊 Система метрик
│   └── logger.py                   # 📝 Продвинутое логирование  
├── admin/
│   └── admin.py                    # 👑 Админская панель
└── deployment/
    ├── Dockerfile                  # 🐳 Multi-stage production build
    ├── docker-compose.yml          # 🚀 Orchestration
    ├── Makefile                    # 🛠️ Automation
    └── han-dating-bot.service      # 🔧 Systemd integration
```
## 🚀 Быстрый старт

### 📦 Миграция данных (v2.0+)

Если у вас есть данные в старом формате `girls_data.json`, используйте скрипт миграции:

```bash
# Автоматическая миграция из girls_data.json в girls_data/{chat_id}.json
python migrate_girls_data.py

# Ручная миграция (если нужно)
mv girls_data.json girls_data.json.backup
mkdir girls_data
# Затем запустите бота - он создаст новую структуру автоматически
```

### Локальная разработка

```bash
# 1. Клонирование и установка зависимостей
git clone <repository-url>
cd han-dating-bot
make dev-setup

# 2. Конфигурация
cp .env.production .env
# Отредактируйте .env файл с вашими API ключами

# 3. Запуск
make run
```

### Docker Deployment

```bash
# 1. Сборка и запуск
make docker-build
make docker-run

# 2. Мониторинг
make docker-logs

# 3. Остановка
make docker-stop
```

### Production Deployment

```bash
# 1. Подготовка production окружения
make production-setup

# 2. Установка systemd service
make systemd-install

# 3. Запуск
sudo systemctl start han-dating-bot

# 4. Мониторинг
make status
make logs
```

## ⚙️ Конфигурация

### Обязательные параметры

```env
# Telegram API (получить на my.telegram.org)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash  
TELEGRAM_PHONE=+1234567890

# OpenAI API (получить на platform.openai.com)
OPENAI_API_KEY=sk-...

# Администратор бота
ADMIN_CHAT_ID=your_telegram_user_id
```

### Production параметры

```env
# Производительность
HISTORY_LIMIT=20
RATE_LIMIT_REQUESTS=5
MAX_RETRIES=5

# Мониторинг
ENABLE_METRICS=true
HEALTH_CHECK_INTERVAL=300

# Логирование
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
```

## 🎛️ Админские команды

Все команды доступны пользователю с `ADMIN_CHAT_ID`:

### 📊 Мониторинг
- `!status` - Статус системы и основные метрики
- `!metrics` - Детальные метрики производительности

### 👥 Управление профилями  
- `!list` - Список всех профилей
- `!add <chat_id> <name>` - Добавить новый профиль
- `!del <chat_id>` - Удалить профиль
- `!profile <chat_id>` - Подробная информация о профиле

### 🚀 Действия
- `!start <chat_id>` - Инициировать диалог с пользователем
- `!id [query]` - Получить информацию о пользователе

### 🔧 Система
- `!restart` - Перезапуск бота (планируется)
- `!stop` - Безопасная остановка
- `!help` - Справка по командам

## 📊 Мониторинг

### Встроенные метрики

- **Uptime** - Время работы системы
- **Messages** - Статистика входящих/исходящих сообщений  
- **API Performance** - Успешность и время ответа OpenAI
- **Memory Usage** - Использование памяти процессом
- **Active Chats** - Количество активных диалогов
- **Error Rate** - Частота ошибок

### Health Checks

```bash
# Проверка состояния
curl http://localhost:8001/health

# Prometheus метрики  
curl http://localhost:8000/metrics
```

### Логирование

```bash
# Просмотр логов в реальном времени
tail -f logs/bot.log

# Системные логи (systemd)
sudo journalctl -u han-dating-bot -f

# Docker логи
docker-compose logs -f hanbot
```
requirements.txt         # Dependencies
```

## Requirements
- Python 3.10+
- A Telegram account and API credentials
- An OpenAI API key (optional for offline fallback tests)

## Installation
1. Create and activate a virtual environment
   - macOS/Linux (zsh):
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - Windows (PowerShell):
     ```powershell
     py -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

## Configuration (.env)
Copy `.env.example` to `.env` and fill in values:
```
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=+10000000000
SESSION_NAME=han_session

ADMIN_CHAT_ID=123456789
ADMIN_BOT_API_KEY=

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.85
OPENAI_MAX_TOKENS=240

HISTORY_LIMIT=20
PROFILE_ANALYZE_EVERY_N=12
GIRLS_DATA_PATH=girls_data
CONVERSATIONS_DIR=conversations
BACKUPS_DIR=backups
LOG_FILE=bot.log
LOG_LEVEL=INFO
```

If `OPENAI_API_KEY` is empty the bot will return a safe fallback phrase instead of calling the API.

## Running
First login with Telethon (one-time):
```bash
python main.py
```
It will prompt for the phone and possibly 2FA. The file `han_session.session` will be created and should not be committed.

## Admin commands (DM from ADMIN_CHAT_ID)
- `!help` — list commands
- `!id [query]` — show your id or resolve username/link/phone/id
- `!add <chat_id> <name>` — ensure profile and set name
- `!list` — list all profiles
- `!del <chat_id>` — delete profile
- `!profile <chat_id>` — dump profile dict
- `!start <chat_id>` — start a conversation with a time-of-day message
- `!stop` — graceful shutdown

## Tests
This repo contains an async test harness `test.py` that uses mocks for OpenAI and covers:
- Response generation, fallbacks, history, error handling, context
- Conversation initiator (time_of_day, generate_starter)
- Autonomous manager tick and follow-up
- Admin command processing
- Girls manager CRUD, analyze/summarize, daily backup
- Logger setup and append_conversation
- Shutdown handler flow
- Basic config checks and main import smoke test

Run tests:
```bash
python test.py            # offline mocked tests
python test.py --real-api # includes live OpenAI tests if key is set
```

## Notes
- The project stores data locally in JSON; make sure `.gitignore` keeps conversations, backups and session files out of git.
- Time-window logic for autonomous actions avoids late-night messaging.

## License (MIT)
```
MIT License

Copyright (c) 2025 Han

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

# Han Telegram Dater Bot (RU)

Телеграм-бот-собеседник, поддерживающий тёплый, уважительный диалог, ведущий профиль собеседницы и историю общения, а также способный инициировать разговоры и делать фоллоу-апы. Построен на async Python, Telethon и OpenAI Responses API.

## Возможности
- Генерация ответов через OpenAI Responses API
- Краткая история сообщений в памяти по chat_id
- Простая выжимка фактов из входящих сообщений
- Хранение данных в `girls_data/{chat_id}.json` (индивидуальные файлы профилей)
- Логи разговоров в `conversations/<chat_id>.json`
- Ежедневные бэкапы в `backups/<chat_id>/YYYY-MM-DD.json`
- Админ-команды в личке
- Автономные стартеры и фоллоу-апы с естественными задержками
- Корректная остановка по сигналам

## Установка и запуск
1. Создать виртуальное окружение и установить зависимости (см. раздел Installation выше)
2. Заполнить `.env` (см. Configuration)
3. Запустить: `python main.py`

## Тесты
Запуск тестов:
```
python test.py
python test.py --real-api
```

## Лицензия (MIT)
Программное обеспечение распространяется по лицензии MIT (см. текст выше).
