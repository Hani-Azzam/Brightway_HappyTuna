"""Durable memory for one employee — cursors + episodic history.

Two jobs (KB §2.6, §2.4/§6.6):
  - **cursors**: where each channel was last read, so the employee resumes after a
    restart instead of re-reading (and re-reacting to) old messages;
  - **episodes**: a time-ordered record of what it saw / did / was denied, so it can
    recall "I already reported this" and so a run is auditable and replayable.

Same plain-SQLite style as the activation store. `BITRIX_EMPLOYEE_DB`
overrides the path (tests point it at a temp file).
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "employee.db"


def _db_path() -> Path:
    return Path(os.environ.get("BITRIX_EMPLOYEE_DB", str(_DEFAULT_DB)))


def _connection() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cursors (
            employee_id TEXT NOT NULL,
            channel_id  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            PRIMARY KEY (employee_id, channel_id)
        );
        CREATE TABLE IF NOT EXISTS episodes (
            id             TEXT PRIMARY KEY,
            employee_id    TEXT NOT NULL,
            kind           TEXT NOT NULL,     -- ACTIVATED | OBSERVED | ACTED | DENIED
            ref            TEXT,
            summary        TEXT,
            correlation_id TEXT,
            ts             TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class EmployeeMemory:
    def __init__(self, employee_id: str) -> None:
        self._employee_id = employee_id

    # --- cursors (satisfies Perception's cursor-store protocol) ---

    def get_cursor(self, channel_id: str) -> str | None:
        with _connection() as conn:
            row = conn.execute(
                "SELECT last_seen FROM cursors WHERE employee_id = ? AND channel_id = ?",
                (self._employee_id, channel_id),
            ).fetchone()
        return row["last_seen"] if row else None

    def set_cursor(self, channel_id: str, ts: str) -> None:
        with _connection() as conn:
            conn.execute(
                "INSERT INTO cursors (employee_id, channel_id, last_seen) VALUES (?, ?, ?) "
                "ON CONFLICT(employee_id, channel_id) DO UPDATE SET last_seen = excluded.last_seen",
                (self._employee_id, channel_id, ts),
            )
            conn.commit()

    # --- episodic ---

    def remember(
        self,
        kind: str,
        *,
        ref: str | None = None,
        summary: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        with _connection() as conn:
            conn.execute(
                "INSERT INTO episodes (id, employee_id, kind, ref, summary, correlation_id, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), self._employee_id, kind, ref, summary, correlation_id, _now()),
            )
            conn.commit()

    def recent(self, kind: str | None = None, limit: int = 10) -> list[dict]:
        """Newest-first episodes for this employee, optionally filtered by kind."""
        with _connection() as conn:
            if kind is None:
                rows = conn.execute(
                    "SELECT * FROM episodes WHERE employee_id = ? ORDER BY ts DESC LIMIT ?",
                    (self._employee_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM episodes WHERE employee_id = ? AND kind = ? "
                    "ORDER BY ts DESC LIMIT ?",
                    (self._employee_id, kind, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def has_acted_on(self, ref: str) -> bool:
        with _connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM episodes WHERE employee_id = ? AND kind = 'ACTED' AND ref = ? LIMIT 1",
                (self._employee_id, ref),
            ).fetchone()
        return row is not None
