"""PostgreSQL backend — durable production state (KB §2.3).

Same contract as the SQLite store (`StoreProtocol`), so the service layer is
unchanged. Differences that matter for a real deployment:

- **`seq` comes from a shared Postgres SEQUENCE** (`chat_seq`), not an in-process
  counter, so ordering stays globally monotonic across restarts and concurrent
  writers (the SQLite `IdFactory.next_seq()` would reset/collide there).
- A connection **pool** is used instead of connect-per-call.
- The `messages` table stays **append-only** — it is the durable, ordered event
  log the KB asks for (§2.4). Time + string ids still come from the injected
  `Clock`/`IdFactory` so the caller controls those.

`psycopg` is imported lazily so importing this module never requires the driver
(the test suite runs on SQLite).
"""
from __future__ import annotations

import json

from services.internal_messaging.integration.clock import Clock
from services.internal_messaging.integration.ids import IdFactory

_SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS chat_seq;
CREATE TABLE IF NOT EXISTS channels (
    id             TEXT PRIMARY KEY,
    type           TEXT NOT NULL,
    name           TEXT,
    correlation_id TEXT,
    sim_time       TEXT NOT NULL,
    seq            BIGINT NOT NULL
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
    seq            BIGINT NOT NULL,
    channel_id     TEXT NOT NULL,
    sender_id      TEXT NOT NULL,
    body           TEXT NOT NULL,
    source         TEXT NOT NULL,
    trust_label    TEXT NOT NULL,
    mentions       TEXT NOT NULL,
    correlation_id TEXT,
    sim_time       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_channel_seq ON messages(channel_id, seq);
CREATE INDEX IF NOT EXISTS idx_messages_seq ON messages(seq);
"""


class PostgresStore:
    def __init__(self, dsn: str, clock: Clock, ids: IdFactory) -> None:
        from psycopg_pool import ConnectionPool  # lazy: only needed for Postgres

        self._clock = clock
        self._ids = ids
        self._pool = ConnectionPool(dsn, min_size=1, open=True, kwargs={"autocommit": True})
        self._init()

    def _init(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(_SCHEMA)

    def _rows(self, conn):
        from psycopg.rows import dict_row

        return conn.cursor(row_factory=dict_row)

    def _next_seq(self, conn) -> int:
        return conn.execute("SELECT nextval('chat_seq') AS s").fetchone()[0]

    # --- channels & membership -------------------------------------------

    def create_channel(
        self, channel_type: str, name: str | None, correlation_id: str | None,
        creator: str, members: list[str],
    ) -> dict:
        channel_id = self._ids.new("chan")
        now = self._clock.now().isoformat()
        with self._pool.connection() as conn:
            seq = self._next_seq(conn)
            conn.execute(
                "INSERT INTO channels (id, type, name, correlation_id, sim_time, seq) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (channel_id, channel_type, name, correlation_id, now, seq),
            )
            seen: set[str] = set()
            conn.execute(
                "INSERT INTO memberships (channel_id, agent_id, role, sim_time) "
                "VALUES (%s, %s, 'owner', %s)",
                (channel_id, creator, now),
            )
            seen.add(creator)
            for agent_id in members:
                if agent_id in seen:
                    continue
                conn.execute(
                    "INSERT INTO memberships (channel_id, agent_id, role, sim_time) "
                    "VALUES (%s, %s, 'member', %s)",
                    (channel_id, agent_id, now),
                )
                seen.add(agent_id)
        return self.get_channel(channel_id)  # type: ignore[return-value]

    def get_channel(self, channel_id: str) -> dict | None:
        with self._pool.connection() as conn, self._rows(conn) as cur:
            row = cur.execute("SELECT * FROM channels WHERE id = %s", (channel_id,)).fetchone()
        return row

    def add_member(self, channel_id: str, agent_id: str, role: str = "member") -> None:
        now = self._clock.now().isoformat()
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO memberships (channel_id, agent_id, role, sim_time) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (channel_id, agent_id) DO NOTHING",
                (channel_id, agent_id, role, now),
            )

    def is_member(self, channel_id: str, agent_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM memberships WHERE channel_id = %s AND agent_id = %s",
                (channel_id, agent_id),
            ).fetchone()
        return row is not None

    def member_role(self, channel_id: str, agent_id: str) -> str | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT role FROM memberships WHERE channel_id = %s AND agent_id = %s",
                (channel_id, agent_id),
            ).fetchone()
        return row[0] if row else None

    def members(self, channel_id: str) -> list[str]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT agent_id FROM memberships WHERE channel_id = %s "
                "ORDER BY sim_time, agent_id",
                (channel_id,),
            ).fetchall()
        return [r[0] for r in rows]

    def channels_for(self, agent_id: str) -> list[dict]:
        with self._pool.connection() as conn, self._rows(conn) as cur:
            rows = cur.execute(
                "SELECT c.*, "
                "  (SELECT COUNT(*) FROM memberships m2 WHERE m2.channel_id = c.id) AS member_count "
                "FROM channels c JOIN memberships m ON m.channel_id = c.id "
                "WHERE m.agent_id = %s ORDER BY c.seq",
                (agent_id,),
            ).fetchall()
        return rows

    # --- messages (append-only) ------------------------------------------

    def add_message(
        self, channel_id: str, sender_id: str, body: str, source: str,
        trust_label: str, mentions: list[str], correlation_id: str | None,
    ) -> dict:
        message_id = self._ids.new("msg")
        now = self._clock.now().isoformat()
        with self._pool.connection() as conn:
            seq = self._next_seq(conn)
            conn.execute(
                "INSERT INTO messages "
                "(id, seq, channel_id, sender_id, body, source, trust_label, "
                " mentions, correlation_id, sim_time) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (message_id, seq, channel_id, sender_id, body, source,
                 trust_label, json.dumps(mentions), correlation_id, now),
            )
        return self.get_message(message_id)  # type: ignore[return-value]

    def get_message(self, message_id: str) -> dict | None:
        with self._pool.connection() as conn, self._rows(conn) as cur:
            row = cur.execute("SELECT * FROM messages WHERE id = %s", (message_id,)).fetchone()
        return self._decode(row) if row else None

    def messages_since(self, channel_id: str, since: int = 0) -> list[dict]:
        with self._pool.connection() as conn, self._rows(conn) as cur:
            rows = cur.execute(
                "SELECT * FROM messages WHERE channel_id = %s AND seq > %s ORDER BY seq ASC",
                (channel_id, since),
            ).fetchall()
        return [self._decode(r) for r in rows]

    def all_messages_since(self, since: int = 0) -> list[dict]:
        with self._pool.connection() as conn, self._rows(conn) as cur:
            rows = cur.execute(
                "SELECT * FROM messages WHERE seq > %s ORDER BY seq ASC", (since,)
            ).fetchall()
        return [self._decode(r) for r in rows]

    @staticmethod
    def _decode(row: dict) -> dict:
        row["mentions"] = json.loads(row["mentions"])
        return row
