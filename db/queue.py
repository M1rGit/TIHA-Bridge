from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta
from core.message import UniversalMessage
from db.database import _conn

# Задержки retry в секундах
RETRY_DELAYS = [5, 30, 300, 3600]
MAX_RETRIES  = len(RETRY_DELAYS)


class PersistentQueue:

    def push(self, msg: UniversalMessage, sink_platform: str, sink_chat_id: str) -> None:
        with _conn() as con:
            con.execute(
            """INSERT OR IGNORE INTO message_queue
               (id, source_platform, source_chat_id, source_user_id,
                sink_platform, sink_chat_id, text, photo_bytes,
                media_url, source_user_name, source_chat_title,
                timestamp, status, retry_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0)""",
            (
                msg.id, msg.source_platform, msg.source_chat_id, msg.source_user_id,
                sink_platform, sink_chat_id,
                msg.text, msg.photo_bytes,
                msg.media_url, msg.source_user_name, msg.source_chat_title,
                msg.timestamp.isoformat(),
            ),
        )

    def pop_ready(self) -> list[tuple[UniversalMessage, str, str]]:
        now = datetime.utcnow().isoformat()
        with _conn() as con:
            rows = con.execute(
            """SELECT * FROM message_queue
               WHERE status = 'pending'
               AND (next_retry_at IS NULL OR next_retry_at <= ?)
               ORDER BY timestamp ASC""",
            (now,),
        ).fetchall()

        result = []
        for row in rows:
            msg = UniversalMessage(
            id=                row["id"],
            source_platform=   row["source_platform"],
            source_chat_id=    row["source_chat_id"],
            source_user_id=    row["source_user_id"],
            text=              row["text"],
            photo_bytes=       row["photo_bytes"],
            media_url=         row["media_url"] if "media_url" in row.keys() else None,
            source_user_name=  row["source_user_name"] if "source_user_name" in row.keys() else None,
            source_chat_title= row["source_chat_title"] if "source_chat_title" in row.keys() else None,
            timestamp=         datetime.fromisoformat(row["timestamp"]),
            status=            row["status"],
            retry_count=       row["retry_count"],
        )
            result.append((msg, row["sink_platform"], row["sink_chat_id"]))
        return result

    def mark_delivered(self, msg_id: str) -> None:
        now = datetime.utcnow().isoformat()
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM message_queue WHERE id=?", (msg_id,)
            ).fetchone()
            if row:
                con.execute(
                    """INSERT OR REPLACE INTO message_log
                       (id, source_platform, source_chat_id, source_user_id,
                        sink_platform, sink_chat_id, text, status, retry_count, timestamp, delivered_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'delivered', ?, ?, ?)""",
                    (
                        row["id"], row["source_platform"], row["source_chat_id"],
                        row["source_user_id"], row["sink_platform"], row["sink_chat_id"],
                        row["text"], row["retry_count"], row["timestamp"], now,
                    ),
                )
                con.execute("DELETE FROM message_queue WHERE id=?", (msg_id,))

    def mark_failed(self, msg_id: str) -> None:
        with _conn() as con:
            con.execute(
                "UPDATE message_queue SET status='failed' WHERE id=?", (msg_id,)
            )

    def schedule_retry(self, msg_id: str, retry_count: int) -> bool:
        """Планирует следующую попытку. Возвращает False если retry исчерпаны."""
        if retry_count >= MAX_RETRIES:
            self.mark_failed(msg_id)
            return False
        delay   = RETRY_DELAYS[retry_count]
        next_at = (datetime.utcnow() + timedelta(seconds=delay)).isoformat()
        with _conn() as con:
            con.execute(
                "UPDATE message_queue SET retry_count=?, next_retry_at=? WHERE id=?",
                (retry_count + 1, next_at, msg_id),
            )
        return True
