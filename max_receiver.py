import asyncio
import io
from datetime import datetime
from pymax import MaxClient
from pymax.types import Message
import httpx
import bridge
import db

_name_cache: dict[int, str] = {}


async def _fetch_name_background(client: MaxClient, sender_id: int) -> None:
    try:
        await asyncio.sleep(2)
        user = await client.get_user(sender_id)
        if user and user.names:
            n     = user.names[0]
            first = getattr(n, "first_name", "") or getattr(n, "first", "") or ""
            last  = getattr(n, "last_name", "")  or getattr(n, "last", "")  or ""
            name  = f"{first} {last}".strip()
            if name:
                _name_cache[sender_id] = name
    except Exception:
        pass


def _get_sender_name(sender_id: int) -> str:
    return _name_cache.get(sender_id, str(sender_id))


def _get_chat_title(chat_id: int) -> str:
    rows = db.get_max_chats()
    for r in rows:
        if r["chat_id"] == chat_id:
            title = r["title"]
            return title if title != str(chat_id) else str(chat_id)
    return str(chat_id)


async def _download_photo(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        print(f"[Max→TG][ОШИБКА СКАЧИВАНИЯ ФОТО] {e}")
        return None


def register(client: MaxClient) -> None:
    @client.on_raw_receive
    async def handle_raw(data: dict) -> None:
        if data.get("opcode") != 128:
            return

        payload = data.get("payload", {})
        raw_msg = payload.get("message", {})
        chat_id = payload.get("chatId")

        if not raw_msg or not chat_id:
            return

        try:
            msg = Message.from_dict(raw_msg)
        except Exception as e:
            print(f"[Max→TG][ОШИБКА ПАРСИНГА] {e}")
            return

        # Авторегистрация чата
        known = {r["chat_id"] for r in db.get_max_chats()}
        if chat_id not in known:
            all_chats = client.chats + client.dialogs
            found     = next((c for c in all_chats if c.id == chat_id), None)
            title     = getattr(found, "title", None) or str(chat_id)
            db.upsert_max_chat(chat_id, title)
            print(f"[Max] Новый чат зарегистрирован: {title} ({chat_id})")

        if msg.sender and msg.sender not in _name_cache:
            asyncio.create_task(_fetch_name_background(client, msg.sender))

        tg_channel_id = db.get_tg_channel_for_max_chat(chat_id)
        text          = msg.text or ""
        ts            = datetime.fromtimestamp(msg.time / 1000)
        sender_name   = _get_sender_name(msg.sender) if msg.sender else "неизвестен"
        chat_title    = _get_chat_title(chat_id)

        # Извлекаем вложения-фото
        attaches = raw_msg.get("attaches", [])
        photos   = [a for a in attaches if a.get("_type") == "PHOTO" and a.get("baseUrl")]

        db.log_message(
            direction    = "max_to_tg",
            sender_id    = msg.sender,
            recipient_id = tg_channel_id,
            chat_id      = chat_id,
            message_id   = str(msg.id),
            text         = text or "<фото>",
            timestamp    = ts,
        )

        caption = (
            f"💬 {chat_title}\n"
            f"👤 {sender_name}\n"
            f"🕐 {ts.strftime('%d.%m.%Y %H:%M:%S')}"
            + (f"\n\n{text}" if text else "")
        )

        # Кладём в очередь: текст + список URL фото
        await bridge.max_to_tg.put((
            chat_id,
            caption,
            [a["baseUrl"] for a in photos],
        ))
