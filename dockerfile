FROM python:3.12-alpine

# Установка системных зависимостей (ffmpeg для конвертации медиа)
RUN apk update && apk add --no-cache ffmpeg

WORKDIR /app

# Копирование и установка Python-зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY main.py cli.py config.py config.yaml ./
COPY core/ core/
COPY adapters/ adapters/
COPY db/ db/

# Создание директорий для данных (БД, логи, кеш)
RUN mkdir -p data logs cache

# Переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1

# Точка входа
CMD ["python", "main.py"]
