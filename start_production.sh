#!/bin/bash

# Production startup script for Han Dating Bot

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🤖 Han Dating Bot - Production Startup${NC}"
echo "================================================="

# Проверка существования виртуального окружения
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  Виртуальное окружение не найдено. Создаю...${NC}"
    python3 -m venv venv
fi

# Активация виртуального окружения
echo -e "${BLUE}📦 Активация виртуального окружения...${NC}"
source venv/bin/activate

# Обновление pip
echo -e "${BLUE}⬆️  Обновление pip...${NC}"
pip install --upgrade pip

# Установка зависимостей
echo -e "${BLUE}📋 Установка зависимостей...${NC}"
pip install -r requirements.txt

# Проверка конфигурации
echo -e "${BLUE}⚙️  Проверка конфигурации...${NC}"
if [ ! -f ".env" ] && [ ! -f ".env.production" ]; then
    echo -e "${RED}❌ Файл конфигурации (.env или .env.production) не найден!${NC}"
    echo "Создайте файл .env на основе .env.production"
    exit 1
fi

# Создание необходимых директорий
echo -e "${BLUE}📁 Создание директорий...${NC}"
mkdir -p data/conversations
mkdir -p data/backups  
mkdir -p logs

# Проверка доступности портов
echo -e "${BLUE}🔌 Проверка портов...${NC}"
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Порт 8000 уже используется${NC}"
fi

if lsof -Pi :8001 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Порт 8001 уже используется${NC}"
fi

# Проверка синтаксиса Python
echo -e "${BLUE}🐍 Проверка синтаксиса...${NC}"
python -m py_compile main.py
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Синтаксис корректен${NC}"
else
    echo -e "${RED}❌ Ошибки синтаксиса в main.py${NC}"
    exit 1
fi

# Запуск бота
echo -e "${GREEN}🚀 Запуск Han Dating Bot...${NC}"
echo "================================================="

# Логирование в файл и stdout
python main.py 2>&1 | tee -a logs/startup.log
