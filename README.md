# TIHA-Bridge

Мост между мессенджером Max, Telegram и Discord. Пересылает сообщения между платформами.

## Возможности

- Пересылка входящих сообщений из Max групп в привязанные TG каналы и Discord
- Отправка сообщений из TG/Discord в Max
- Пересылка сообщений из ЛС TG бота в выбранный Max чат
- Управление связками и маршрутизацией через CLI
- Логирование всех сообщений в SQLite
- Поддержка медиа (аудио/видео конвертация через ffmpeg)

## Структура проекта

```
TIHA-Bridge/
├── main.py             # точка входа
├── cli.py              # CLI для управления
├── config.py           # загрузка переменных окружения
├── config.yaml         # включение/отключение адаптеров
├── requirements.txt    # Python зависимости
├── dockerfile          # Docker образ
├── .env.example        # шаблон переменных окружения
├── core/               # ядро: адаптер, шина, маршрутизация, медиа
├── adapters/           # адаптеры платформ (max, telegram, discord)
└── db/                 # работа с БД (bridge.db, messages.db)
```

## Установка

**Требования:** Python 3.11+

### Локальный запуск

```bash
git clone <repo>
cd TIHA-Bridge

python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### Docker

```bash
# Сборка образа
docker build -t tiha-bridge .

# Запуск с файлом окружения
docker run -d \
  --name tiha-bridge \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/cache:/app/cache \
  tiha-bridge
```

## Настройка

**1. Создайте `.env` из шаблона:**
```bash
cp .env.example .env
```

**2. Заполните `.env`:**

| Переменная     | Описание                                              |
|----------------|-------------------------------------------------------|
| `MAX_PHONE`    | Номер телефона аккаунта Max в формате +79001234567    |
| `TG_BOT_TOKEN` | Токен TG бота от @BotFather                           |
| `TG_OWNER_ID`  | Ваш Telegram user_id (узнать у @userinfobot)          |
| `DISCORD_TOKEN`| Токен Discord бота (если включён адаптер Discord)     |

**3. Настройте адаптеры в `config.yaml`:**
```yaml
adapters:
  max: true
  telegram: true
  discord: false  # true для включения Discord
```

**4. Добавьте TG бота в нужные каналы** как администратора с правом публикации.

**5. Запустите:**

Локально:
```bash
python main.py
```

Или в Docker:
```bash
docker run -d --name tiha-bridge --env-file .env -v $(pwd)/data:/app/data tiha-bridge
```

При первом запуске Max попросит подтвердить вход — отсканируйте QR-код через приложение. Сессия сохранится в `cache/session.db`.

## Команды CLI

```bash
# Статус адаптеров
python cli.py status

# Включить/отключить адаптер
python cli.py enable telegram
python cli.py disable discord

# Управление маршрутами
python cli.py route list
python cli.py route add <source> <target>
python cli.py route remove <source> <target>

# Управление админами
python cli.py admin list
python cli.py admin add <platform> <user_id>
python cli.py admin remove <platform> <user_id>
```

## Как это работает

### Регистрация чатов

**Max группы** регистрируются двумя способами:
- Автоматически при старте из списка диалогов аккаунта
- Автоматически при получении первого сообщения из нового чата

**TG каналы** регистрируются автоматически когда бот добавляется в канал.

### Создание связки Max → TG

1. Добавьте TG бота в TG канал как администратора
2. Настройте маршрутизацию через CLI: `python cli.py route add max_channel tg_channel`
3. Сообщения из Max группы будут появляться в TG канале

## База данных

SQLite: **`bridge.db`** (конфигурация) и **`messages.db`** (сообщения).

### bridge.db

| Таблица       | Содержимое                              |
|---------------|-----------------------------------------|
| `chats`       | Зарегистрированные чаты всех платформ   |
| `routes`      | Маршруты между источниками и получателями|
| `settings`    | Настройки (ls_target и т.д.)            |
| `user_names`  | Кеш имён пользователей                  |
| `admins`      | Админы по платформам                    |

### messages.db

| Таблица          | Содержимое                     |
|------------------|--------------------------------|
| `message_queue`  | Очередь сообщений с retry      |
| `message_log`    | Лог всех пересланных сообщений |

## .gitignore
```
.env
cache/
data/
logs/
*.db
__pycache__/
.venv/
```

## Docker Compose (опционально)

Создайте `docker-compose.yml`:
```yaml
version: '3.8'

services:
  bridge:
    build: .
    container_name: tiha-bridge
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./cache:/app/cache
    restart: unless-stopped
```

Запуск:
```bash
docker-compose up -d
```
