from __future__ import annotations
import logging
from db import database as db

logger = logging.getLogger(__name__)


async def resolve_user_name(platform: str, user_id: str, client=None) -> str:
    """
    Возвращает имя пользователя. Сначала смотрит в кеш БД,
    потом пробует получить через клиент платформы.
    """
    cached = db.get_user_name(platform, user_id)
    if cached:
        return cached

    name = None

    if platform == "max" and client is not None:
        try:
            user = await client.get_user(int(user_id))
            if user and user.names:
                n     = user.names[0]
                first = getattr(n, "first_name", "") or getattr(n, "first", "") or ""
                last  = getattr(n, "last_name", "")  or getattr(n, "last", "")  or ""
                name  = f"{first} {last}".strip() or None
        except Exception as e:
            logger.debug("Max user resolve failed for %s: %s", user_id, e)

    elif platform == "telegram" and client is not None:
        try:
            chat = await client.get_chat(int(user_id))
            name = chat.full_name or chat.username or None
        except Exception as e:
            logger.debug("TG user resolve failed for %s: %s", user_id, e)

    elif platform == "discord" and client is not None:
        try:
            user = await client.fetch_user(int(user_id))
            name = user.display_name or user.name or None
        except Exception as e:
            logger.debug("Discord user resolve failed for %s: %s", user_id, e)

    if name:
        db.upsert_user_name(platform, user_id, name)
        return name

    return user_id  # fallback — возвращаем id


def resolve_chat_title(platform: str, chat_id: str) -> str:
    """Возвращает название чата из БД или chat_id как fallback."""
    return db.get_chat_title(platform, chat_id) or chat_id
