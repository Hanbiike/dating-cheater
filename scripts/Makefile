# Makefile for Han Dating Bot

.PHONY: help install test clean lint format type-check docker-build docker-run production-setup

# Переменные
PYTHON := python3
VENV := venv
PIP := $(VENV)/bin/pip
PYTHON_VENV := $(VENV)/bin/python

# Цвета для вывода
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m

help: ## Показать это сообщение
	@echo "$(BLUE)Han Dating Bot - Makefile Commands$(NC)"
	@echo "=================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

install: ## Установить зависимости
	@echo "$(BLUE)📦 Установка зависимостей...$(NC)"
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "$(GREEN)✅ Зависимости установлены$(NC)"

test: ## Запустить тесты
	@echo "$(BLUE)🧪 Запуск тестов...$(NC)"
	$(PYTHON_VENV) test.py

lint: ## Проверить код линтером
	@echo "$(BLUE)🔍 Проверка кода...$(NC)"
	$(PIP) install flake8 black isort mypy
	$(VENV)/bin/flake8 --max-line-length=100 --ignore=E501,W503 *.py
	$(VENV)/bin/black --check --diff *.py
	$(VENV)/bin/isort --check-only --diff *.py

format: ## Форматировать код
	@echo "$(BLUE)🎨 Форматирование кода...$(NC)"
	$(PIP) install black isort
	$(VENV)/bin/black *.py
	$(VENV)/bin/isort *.py
	@echo "$(GREEN)✅ Код отформатирован$(NC)"

type-check: ## Проверить типы
	@echo "$(BLUE)🔎 Проверка типов...$(NC)"
	$(PIP) install mypy
	$(VENV)/bin/mypy --ignore-missing-imports *.py

clean: ## Очистить временные файлы
	@echo "$(BLUE)🧹 Очистка...$(NC)"
	rm -rf __pycache__/
	rm -rf *.pyc
	rm -rf .mypy_cache/
	rm -rf .pytest_cache/
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	@echo "$(GREEN)✅ Очистка завершена$(NC)"

docker-build: ## Собрать Docker образ
	@echo "$(BLUE)🐳 Сборка Docker образа...$(NC)"
	docker build -t han-dating-bot:latest .
	@echo "$(GREEN)✅ Docker образ собран$(NC)"

docker-run: ## Запустить в Docker
	@echo "$(BLUE)🐳 Запуск в Docker...$(NC)"
	docker-compose up -d

docker-stop: ## Остановить Docker контейнеры
	@echo "$(BLUE)🐳 Остановка Docker контейнеров...$(NC)"
	docker-compose down

docker-logs: ## Показать логи Docker контейнера
	docker-compose logs -f hanbot

production-setup: ## Настройка production окружения
	@echo "$(BLUE)⚙️  Настройка production...$(NC)"
	@if [ ! -f ".env" ]; then \
		echo "$(YELLOW)⚠️  Создание .env из .env.production...$(NC)"; \
		cp .env.production .env; \
		echo "$(YELLOW)📝 Отредактируйте .env файл перед запуском$(NC)"; \
	fi
	mkdir -p data/conversations data/backups logs
	chmod +x start_production.sh
	@echo "$(GREEN)✅ Production окружение настроено$(NC)"

run: ## Запустить бота в development режиме  
	@echo "$(BLUE)🤖 Запуск Han Dating Bot...$(NC)"
	$(PYTHON_VENV) main.py

run-production: ## Запустить в production режиме
	@echo "$(BLUE)🚀 Запуск в production режиме...$(NC)"
	./start_production.sh

systemd-install: ## Установить systemd service (требует sudo)
	@echo "$(BLUE)⚙️  Установка systemd service...$(NC)"
	sudo cp han-dating-bot.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable han-dating-bot
	@echo "$(GREEN)✅ Service установлен. Используйте: sudo systemctl start han-dating-bot$(NC)"

status: ## Показать статус service
	sudo systemctl status han-dating-bot

logs: ## Показать логи service  
	sudo journalctl -u han-dating-bot -f

dev-setup: install ## Полная настройка для разработки
	@echo "$(BLUE)🛠️  Настройка окружения разработки...$(NC)"
	$(PIP) install pytest pytest-asyncio black isort mypy flake8
	@echo "$(GREEN)✅ Окружение разработки готово$(NC)"

check: lint type-check ## Полная проверка кода

validate-config: ## Проверить конфигурацию
	@echo "$(BLUE)⚙️  Проверка конфигурации...$(NC)"
	$(PYTHON_VENV) -c "import config; print('✅ Конфигурация корректна')"

backup: ## Создать резервную копию данных
	@echo "$(BLUE)💾 Создание резервной копии...$(NC)"
	tar -czf backup_$(shell date +%Y%m%d_%H%M%S).tar.gz data/ *.session* .env
	@echo "$(GREEN)✅ Резервная копия создана$(NC)"

# Алиасы
start: run
stop: docker-stop
build: docker-build
deploy: production-setup docker-build
all: clean install test lint type-check
