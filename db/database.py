import sqlite3
from pathlib import Path

DB_PATH = Path("bridge.db")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                platform  TEXT NOT NULL,
                chat_id   TEXT NOT NULL,
                title     TEXT NOT NULL,
                PRIMARY KEY (platform, chat_id)
            );

            CREATE TABLE IF NOT EXISTS routes (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                source_platform     TEXT NOT NULL,
                source_chat_id      TEXT NOT NULL,
                sink_platform       TEXT NOT NULL,
                sink_chat_id        TEXT NOT NULL,
                UNIQUE (source_platform, source_chat_id, sink_platform, sink_chat_id)
            );

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

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- Кеш имён пользователей по платформам
            CREATE TABLE IF NOT EXISTS user_names (
                platform  TEXT NOT NULL,
                user_id   TEXT NOT NULL,
                name      TEXT NOT NULL,
                PRIMARY KEY (platform, user_id)
            );
        """)


# --- Chats ---

def upsert_chat(platform: str, chat_id: str, title: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO chats (platform, chat_id, title) VALUES (?, ?, ?)"
            " ON CONFLICT(platform, chat_id) DO UPDATE SET title=excluded.title",
            (platform, chat_id, title),
        )


def get_chats(platform: str) -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            "SELECT chat_id, title FROM chats WHERE platform = ?", (platform,)
        ).fetchall()


def get_chat_title(platform: str, chat_id: str) -> str | None:
    with _conn() as con:
        row = con.execute(
            "SELECT title FROM chats WHERE platform=? AND chat_id=?",
            (platform, chat_id),
        ).fetchone()
        return row["title"] if row else None


# --- Routes ---

def add_route(
    source_platform: str, source_chat_id: str,
    sink_platform: str,   sink_chat_id: str,
) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO routes "
            "(source_platform, source_chat_id, sink_platform, sink_chat_id) "
            "VALUES (?, ?, ?, ?)",
            (source_platform, source_chat_id, sink_platform, sink_chat_id),
        )


def remove_route(route_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM routes WHERE id = ?", (route_id,))


def get_routes_from(source_platform: str, source_chat_id: str) -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            "SELECT id, sink_platform, sink_chat_id FROM routes "
            "WHERE source_platform = ? AND source_chat_id = ?",
            (source_platform, source_chat_id),
        ).fetchall()


def get_all_routes() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("""
            SELECT r.id,
                   r.source_platform, r.source_chat_id,
                   cs.title AS source_title,
                   r.sink_platform, r.sink_chat_id,
                   ct.title AS sink_title
            FROM routes r
            LEFT JOIN chats cs ON cs.platform=r.source_platform AND cs.chat_id=r.source_chat_id
            LEFT JOIN chats ct ON ct.platform=r.sink_platform   AND ct.chat_id=r.sink_chat_id
        """).fetchall()


# --- User names cache ---

def upsert_user_name(platform: str, user_id: str, name: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO user_names (platform, user_id, name) VALUES (?, ?, ?)"
            " ON CONFLICT(platform, user_id) DO UPDATE SET name=excluded.name",
            (platform, user_id, name),
        )


def get_user_name(platform: str, user_id: str) -> str | None:
    with _conn() as con:
        row = con.execute(
            "SELECT name FROM user_names WHERE platform=? AND user_id=?",
            (platform, user_id),
        ).fetchone()
        return row["name"] if row else None


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


# --- Settings ---

def set_setting(key: str, value: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_setting(key: str) -> str | None:
    with _conn() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None
