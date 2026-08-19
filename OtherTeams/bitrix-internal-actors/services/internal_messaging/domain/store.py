"""Persistence for the Internal Messaging System — its own SQLite, stdlib only.

The `messages` table is APPEND-ONLY, so it *is* the immutable, ordered event log
the KB asks for (§2.4) — no separate outbox needed. Ordering is by `seq`
(a single monotonic source), never wall-clock. Time + ids come from the injected
`Clock`/`IdFactory`, so a seeded run is byte-for-byte replayable (§6.6).

No authorization here — this is dumb storage. Rules live in the service layer.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from services.internal_messaging.integration.clock import Clock
from services.internal_messaging.integration.ids import IdFactory


class SqliteStore:
    """SQLite backend — deterministic tests, local dev, and reproducible replay
    (seq/ids come from the injected `IdFactory`). See `PostgresStore` for the
    durable production backend."""

    def __init__(self, db_path: str | Path, clock: Clock, ids: IdFactory) -> None:
        self._db_path = str(db_path)
        self._clock = clock
        self._ids = ids
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _next_seq(self, conn: sqlite3.Connection) -> int:
        """The single monotonic order cursor, derived from the DB (max seq across
        channels + messages, + 1) so it survives service restarts. An in-process
        counter would reset to 1 on every restart and collide, breaking `since`."""
        row = conn.execute(
            "SELECT COALESCE(MAX(s), 0) + 1 AS n FROM ("
            "  SELECT MAX(seq) AS s FROM messages "
            "  UNION ALL SELECT MAX(seq) AS s FROM channels)"
        ).fetchone()
        return row["n"]

    def _init(self) -> None:
        parent = Path(self._db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    id             TEXT PRIMARY KEY,
                    type           TEXT NOT NULL,
                    name           TEXT,
                    correlation_id TEXT,
                    sim_time       TEXT NOT NULL,
                    seq            INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    channel_id TEXT NOT NULL,
                    agent_id   TEXT NOT NULL,
                    role       TEXT NOT NULL DEFAULT 'member',
                    sim_time   TEXT NOT NULL,
                    PRIMARY KEY (channel_id, agent_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id             TEXT PRIMARY KEY,
                    seq            INTEGER NOT NULL,
                    channel_id     TEXT NOT NULL,
                    sender_id      TEXT NOT NULL,
                    body           TEXT NOT NULL,
                    source         TEXT NOT NULL,
                    trust_label    TEXT NOT NULL,
                    mentions       TEXT NOT NULL,
                    correlation_id TEXT,
                    sim_time       TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_channel_seq
                    ON messages(channel_id, seq);
                CREATE INDEX IF NOT EXISTS idx_messages_seq ON messages(seq);
                """
            )
            conn.commit()

    # --- channels & membership -------------------------------------------

    def create_channel(
        self,
        channel_type: str,
        name: str | None,
        correlation_id: str | None,
        creator: str,
        members: list[str],
    ) -> dict:
        channel_id = self._ids.new("chan")
        now = self._clock.now().isoformat()
        with self._connect() as conn:
            seq = self._next_seq(conn)
            conn.execute(
                "INSERT INTO channels (id, type, name, correlation_id, sim_time, seq) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (channel_id, channel_type, name, correlation_id, now, seq),
            )
            seen: set[str] = set()
            conn.execute(
                "INSERT INTO memberships (channel_id, agent_id, role, sim_time) "
                "VALUES (?, ?, 'owner', ?)",
                (channel_id, creator, now),
            )
            seen.add(creator)
            for agent_id in members:
                if agent_id in seen:
                    continue
                conn.execute(
                    "INSERT INTO memberships (channel_id, agent_id, role, sim_time) "
                    "VALUES (?, ?, 'member', ?)",
                    (channel_id, agent_id, now),
                )
                seen.add(agent_id)
            conn.commit()
        return self.get_channel(channel_id)  # type: ignore[return-value]

    def get_channel(self, channel_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE id = ?", (channel_id,)
            ).fetchone()
        return dict(row) if row else None

    def add_member(self, channel_id: str, agent_id: str, role: str = "member") -> None:
        now = self._clock.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO memberships (channel_id, agent_id, role, sim_time) "
                "VALUES (?, ?, ?, ?)",
                (channel_id, agent_id, role, now),
            )
            conn.commit()

    def is_member(self, channel_id: str, agent_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM memberships WHERE channel_id = ? AND agent_id = ?",
                (channel_id, agent_id),
            ).fetchone()
        return row is not None

    def member_role(self, channel_id: str, agent_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT role FROM memberships WHERE channel_id = ? AND agent_id = ?",
                (channel_id, agent_id),
            ).fetchone()
        return row["role"] if row else None

    def members(self, channel_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT agent_id FROM memberships WHERE channel_id = ? ORDER BY sim_time, agent_id",
                (channel_id,),
            ).fetchall()
        return [r["agent_id"] for r in rows]

    def channels_for(self, agent_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.*, "
                "  (SELECT COUNT(*) FROM memberships m2 WHERE m2.channel_id = c.id) AS member_count "
                "FROM channels c "
                "JOIN memberships m ON m.channel_id = c.id "
                "WHERE m.agent_id = ? ORDER BY c.seq",
                (agent_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- messages (append-only) ------------------------------------------

    def add_message(
        self,
        channel_id: str,
        sender_id: str,
        body: str,
        source: str,
        trust_label: str,
        mentions: list[str],
        correlation_id: str | None,
    ) -> dict:
        message_id = self._ids.new("msg")
        now = self._clock.now().isoformat()
        with self._connect() as conn:
            seq = self._next_seq(conn)
            conn.execute(
                "INSERT INTO messages "
                "(id, seq, channel_id, sender_id, body, source, trust_label, "
                " mentions, correlation_id, sim_time) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message_id, seq, channel_id, sender_id, body, source,
                    trust_label, json.dumps(mentions), correlation_id, now,
                ),
            )
            conn.commit()
        return self.get_message(message_id)  # type: ignore[return-value]

    def get_message(self, message_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["mentions"] = json.loads(d["mentions"])
        return d

    def messages_since(self, channel_id: str, since: int = 0) -> list[dict]:
        """Channel history with seq > `since`, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE channel_id = ? AND seq > ? ORDER BY seq ASC",
                (channel_id, since),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def all_messages_since(self, since: int = 0) -> list[dict]:
        """CROSS-CHANNEL history with seq > `since`, oldest first — the activation
        firehose. No channel filter: the append-only `messages` table IS the ordered
        event log, so a single seq cursor replays every post in order (§2.4/§6)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE seq > ? ORDER BY seq ASC", (since,)
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["mentions"] = json.loads(d["mentions"])
        return d


# Back-compat alias: existing callers/tests build `Store(db_path, clock, ids)`.
Store = SqliteStore
