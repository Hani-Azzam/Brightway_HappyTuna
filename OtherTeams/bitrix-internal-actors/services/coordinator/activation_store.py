"""Durable log of every activation the coordinator makes.

This is the audit / replay artifact the KB asks for (§2.4 event sourcing, §6.6
reproducibility) — polling alone would leave no record, so we write one row per
"event X activated agent Y at time T". Plain-SQLite style;
`BITRIX_COORD_DB` overrides the path (tests point it at a temp file).
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services.coordinator.events import ActivationEvent

_DEFAULT_DB = Path(__file__).parent / "data" / "activations.db"


def _db_path() -> Path:
    return Path(os.environ.get("BITRIX_COORD_DB", str(_DEFAULT_DB)))


def _connection() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activations (
            id             TEXT PRIMARY KEY,
            agent_id       TEXT NOT NULL,
            event_kind     TEXT NOT NULL,
            event_name     TEXT,
            channel_id     TEXT,
            message_id     TEXT,
            correlation_id TEXT,
            actor_id       TEXT,
            activated_at   TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def record(agent_id: str, event: ActivationEvent) -> str:
    activation_id = str(uuid.uuid4())
    with _connection() as conn:
        conn.execute(
            "INSERT INTO activations "
            "(id, agent_id, event_kind, event_name, channel_id, message_id, "
            " correlation_id, actor_id, activated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                activation_id,
                agent_id,
                event.kind,
                event.name,
                event.channel_id,
                event.message_id,
                event.correlation_id,
                event.actor_id,
                _now(),
            ),
        )
        conn.commit()
    return activation_id


def list_all() -> list[dict]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM activations ORDER BY activated_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]
