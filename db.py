import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("bridge.db")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS max_chats (
                chat_id   INTEGER PRIMARY KEY,
                title     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tg_channels (
                channel_id  INTEGER PRIMARY KEY,
                title       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS links (
                max_chat_id    INTEGER NOT NULL REFERENCES max_chats(chat_id),
                tg_channel_id  INTEGER NOT NULL REFERENCES tg_channels(channel_id),
                PRIMARY KEY (max_chat_id, tg_channel_id)
            );

            CREATE TABLE IF NOT EXISTS message_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                direction     TEXT NOT NULL,
                sender_id     INTEGER,
                recipient_id  INTEGER,
                chat_id       INTEGER,
                message_id    TEXT,
                text          TEXT,
                timestamp     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ls_target (
                chat_id INTEGER NOT NULL
            );
        """)


# --- Max chats ---

def upsert_max_chat(chat_id: int, title: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO max_chats (chat_id, title) VALUES (?, ?)"
            " ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title",
            (chat_id, title),
        )


def get_max_chats() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("SELECT chat_id, title FROM max_chats").fetchall()


# --- TG channels ---

def upsert_tg_channel(channel_id: int, title: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO tg_channels (channel_id, title) VALUES (?, ?)"
            " ON CONFLICT(channel_id) DO UPDATE SET title=excluded.title",
            (channel_id, title),
        )


def get_tg_channels() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("SELECT channel_id, title FROM tg_channels").fetchall()


# --- Links ---

def add_link(max_chat_id: int, tg_channel_id: int) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO links (max_chat_id, tg_channel_id) VALUES (?, ?)",
            (max_chat_id, tg_channel_id),
        )


def remove_link(max_chat_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM links WHERE max_chat_id = ?", (max_chat_id,))


def get_tg_channel_for_max_chat(max_chat_id: int) -> int | None:
    with _conn() as con:
        row = con.execute(
            "SELECT tg_channel_id FROM links WHERE max_chat_id = ?",
            (max_chat_id,),
        ).fetchone()
        return row["tg_channel_id"] if row else None


def get_all_links() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("""
            SELECT m.title AS max_title, m.chat_id,
                   t.title AS tg_title, t.channel_id
            FROM links l
            JOIN max_chats m ON m.chat_id = l.max_chat_id
            JOIN tg_channels t ON t.channel_id = l.tg_channel_id
        """).fetchall()


# --- Logging ---

def log_message(
    direction: str,       # 'max_to_tg' | 'tg_to_max'
    sender_id: int | None,
    recipient_id: int | None,
    chat_id: int | None,
    text: str,
    message_id: str | None = None,
    timestamp: datetime | None = None,
) -> None:
    ts = (timestamp or datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as con:
        con.execute(
            """INSERT INTO message_log
               (direction, sender_id, recipient_id, chat_id, message_id, text, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (direction, sender_id, recipient_id, chat_id, message_id, text, ts),
        )

# --- ЛС бот → Max ---

def set_ls_target_chat(chat_id: int) -> None:
    """Сохраняет целевой Max чат для сообщений из ЛС бота."""
    with _conn() as con:
        con.execute("DELETE FROM ls_target")
        con.execute("INSERT INTO ls_target (chat_id) VALUES (?)", (chat_id,))


def get_ls_target_chat() -> int | None:
    """Возвращает целевой Max чат для сообщений из ЛС бота."""
    with _conn() as con:
        row = con.execute("SELECT chat_id FROM ls_target").fetchone()
        return row["chat_id"] if row else None
