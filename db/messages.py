import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from core.message import UniversalMessage

DB_PATH = Path("messages.db")
BRIDGE_DB_PATH = Path("bridge.db")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS message_queue (
                id                TEXT PRIMARY KEY,
                source_platform   TEXT NOT NULL,
                source_chat_id    TEXT NOT NULL,
                source_user_id    TEXT NOT NULL,
                sink_platform     TEXT NOT NULL,
                sink_chat_id      TEXT NOT NULL,
                text              TEXT NOT NULL,
                photo_bytes       BLOB,
                media_url         TEXT,
                source_user_name  TEXT,
                source_chat_title TEXT,
                timestamp         TEXT NOT NULL,
                status            TEXT NOT NULL DEFAULT 'pending',
                retry_count       INTEGER NOT NULL DEFAULT 0,
                next_retry_at     TEXT
            );

            CREATE TABLE IF NOT EXISTS message_log (
                id              TEXT PRIMARY KEY,
                source_platform TEXT NOT NULL,
                source_chat_id  TEXT NOT NULL,
                source_chat_title TEXT,
                source_user_id  TEXT NOT NULL,
                source_user_name TEXT,
                sink_platform   TEXT NOT NULL,
                sink_chat_id    TEXT NOT NULL,
                text            TEXT NOT NULL,
                media_url       TEXT,
                status          TEXT NOT NULL,
                retry_count     INTEGER NOT NULL,
                timestamp       TEXT NOT NULL,
                delivered_at    TEXT
            );
        """)

    # Миграция: удаляем старые таблицы из bridge.db если они остались
    if BRIDGE_DB_PATH.exists():
        try:
            with sqlite3.connect(BRIDGE_DB_PATH) as con:
                con.execute("DROP TABLE IF EXISTS message_log")
                con.execute("DROP TABLE IF EXISTS message_queue")
        except Exception:
            pass


# --- Message log ---

def log_message(
    msg_id: str,
    source_platform: str,
    source_chat_id: str,
    source_chat_title: str | None,
    source_user_id: str,
    source_user_name: str | None,
    sink_platform: str,
    sink_chat_id: str,
    text: str,
    media_url: str | None,
    status: str,
    retry_count: int,
    timestamp: str,
    delivered_at: str | None = None,
) -> None:
    with _conn() as con:
        con.execute(
            """INSERT OR REPLACE INTO message_log
               (id, source_platform, source_chat_id, source_chat_title,
                source_user_id, source_user_name, sink_platform, sink_chat_id,
                text, media_url, status, retry_count, timestamp, delivered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_id, source_platform, source_chat_id, source_chat_title,
                source_user_id, source_user_name, sink_platform, sink_chat_id,
                text, media_url, status, retry_count, timestamp, delivered_at,
            ),
        )


def log_outgoing_message(
    source_platform: str,
    source_chat_id: str,
    source_user_id: str,
    source_user_name: str | None,
    source_chat_title: str | None,
    sink_platform: str,
    sink_chat_id: str,
    text: str,
    media_url: str | None,
) -> None:
    """Логирует сообщение, отправленное напрямую (минуя MessageBus)."""
    import uuid
    msg_id = f"out-{uuid.uuid4()}"
    now = datetime.utcnow().isoformat()
    log_message(
        msg_id=msg_id,
        source_platform=source_platform,
        source_chat_id=source_chat_id,
        source_chat_title=source_chat_title,
        source_user_id=source_user_id,
        source_user_name=source_user_name,
        sink_platform=sink_platform,
        sink_chat_id=sink_chat_id,
        text=text,
        media_url=media_url,
        status="delivered",
        retry_count=0,
        timestamp=now,
        delivered_at=now,
    )


# --- Message queue ---

# Задержки retry в секундах
RETRY_DELAYS = [5, 30, 300, 3600]
MAX_RETRIES = len(RETRY_DELAYS)


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
        delay = RETRY_DELAYS[retry_count]
        next_at = (datetime.utcnow() + timedelta(seconds=delay)).isoformat()
        with _conn() as con:
            con.execute(
                "UPDATE message_queue SET retry_count=?, next_retry_at=? WHERE id=?",
                (retry_count + 1, next_at, msg_id),
            )
        return True
