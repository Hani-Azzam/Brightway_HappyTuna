import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "data" / "email.db"


def _connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    with _connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id        TEXT PRIMARY KEY,
                from_addr TEXT NOT NULL,
                to_addr   TEXT NOT NULL,
                subject   TEXT NOT NULL,
                body      TEXT NOT NULL,
                sent_at   TEXT NOT NULL,
                is_read   INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()


_init()


def send(from_addr: str, to_addr: str, subject: str, body: str) -> str:
    """Store a new email and return its generated ID."""
    email_id = str(uuid.uuid4())
    sent_at = datetime.utcnow().isoformat(timespec="seconds")
    with _connection() as conn:
        conn.execute(
            "INSERT INTO emails (id, from_addr, to_addr, subject, body, sent_at, is_read) "
            "VALUES (?, ?, ?, ?, ?, ?, 0)",
            (email_id, from_addr, to_addr, subject, body, sent_at),
        )
        conn.commit()
    return email_id


def count_unread(address: str) -> int:
    with _connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM emails WHERE to_addr = ? AND is_read = 0",
            (address,),
        ).fetchone()
    return row["n"]

def get_inbox(address: str) -> list[dict]:
    """Return all emails for an address, newest first."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM emails WHERE to_addr = ? ORDER BY sent_at DESC",
            (address,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_unread(address: str) -> list[dict]:
    """Return only 1 unread email for an address, oldest email."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM emails WHERE to_addr = ? AND is_read = 0 ORDER BY sent_at ASC LIMIT 1",
            (address,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_read(email_id: str) -> None:
    with _connection() as conn:
        conn.execute("UPDATE emails SET is_read = 1 WHERE id = ?", (email_id,))
        conn.commit()


def mark_all_read(address: str) -> None:
    with _connection() as conn:
        conn.execute("UPDATE emails SET is_read = 1 WHERE to_addr = ?", (address,))
        conn.commit()
