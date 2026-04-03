Перераспределение трафика сервисов:
```
Max -> None
Telegram -> VPN
Discord -> VPN
```

**CLI (`python cli.py`)**

- `status` — состояние адаптеров
- `enable <platform>` — включить адаптер
- `disable <platform>` — выключить адаптер
- `toggle <platform>` — переключить адаптер
- `route list` — все маршруты
- `route add <src_platform> <src_chat_id> <sink_platform> <sink_chat_id>` — добавить маршрут
- `route remove <route_id>` — удалить маршрут
- `admin list` — все админы по платформам
- `admin add <platform> <user_id>` — добавить админа
- `admin remove <platform> <user_id>` — удалить админа

---

**Telegram (только для owner и админов)**

- `/start` — справка
- `/routes` — список маршрутов
- `/addroute` — добавить маршрут (интерактивно через кнопки)
- `/delroute` — удалить маршрут (через кнопки)
- `/setchat` — задать целевой чат для пересылки личных сообщений
- `/admins` — список Telegram-админов бота

---

**Discord (только для админов из БД)**

- `/routes` — список маршрутов
- `/addroute <src_platform> <src_chat_id> <sink_platform> <sink_chat_id>` — добавить маршрут
- `/delroute <route_id>` — удалить маршрут
- `/admins` — список Discord-админов бота
