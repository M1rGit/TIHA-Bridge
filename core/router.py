from __future__ import annotations
from core.message import UniversalMessage
from db import database as db


class Router:
    def get_targets(self, msg: UniversalMessage) -> list[tuple[str, str]]:
        """Возвращает список (sink_platform, sink_chat_id) для сообщения."""
        rows = db.get_routes_from(msg.source_platform, msg.source_chat_id)
        return [(r["sink_platform"], r["sink_chat_id"]) for r in rows]
