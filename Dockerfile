# Multi-stage build для production
FROM python:3.11-slim as builder

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Создание пользователя для безопасности
RUN groupadd -r hanbot && useradd -r -g hanbot hanbot

# Установка runtime зависимостей
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Копирование установленных пакетов
COPY --from=builder /root/.local /home/hanbot/.local

# Создание рабочей директории
WORKDIR /app

# Копирование кода приложения
COPY . .

# Установка владельца файлов
RUN chown -R hanbot:hanbot /app

# Создание директорий для данных
RUN mkdir -p /app/data/conversations /app/data/backups /app/logs && \
    chown -R hanbot:hanbot /app/data /app/logs

# Переключение на непривилегированного пользователя
USER hanbot

# Добавление локального bin в PATH
ENV PATH=/home/hanbot/.local/bin:$PATH

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV GIRLS_DATA_PATH=/app/data/girls_data.json
ENV CONVERSATIONS_DIR=/app/data/conversations
ENV BACKUPS_DIR=/app/data/backups
ENV LOG_FILE=/app/logs/bot.log
ENV METRICS_FILE=/app/data/metrics.json

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health')" || exit 1

# Экспорт портов для мониторинга
EXPOSE 8000 8001

# Запуск приложения
CMD ["python", "main.py"]
