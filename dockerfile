FROM python:3.12-alpine

RUN apk update && \
    apk add ffmpeg --no-cache

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY db .
COPY core .
COPY adapters/discord .
COPY adapters/max .
COPY adapters/telegram .

CMD ["python", "main.py"]
