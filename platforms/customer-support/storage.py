import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from models import (
    Ticket,
    TicketCreate,
    TicketPatch,
    ActivityLogEntry,
    TicketStatus,
)

# ------------------------------------------------------------------
# Database location. Overridable via env var so tests/CI can use a
# throwaway file or ":memory:" without touching the real data.
# ------------------------------------------------------------------
DB_PATH = os.environ.get("CS_DB_PATH", "customer_support.db")


@contextmanager
def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and counters if they don't exist yet. Safe to call
    every startup — CREATE TABLE IF NOT EXISTS is a no-op on existing data."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                linked_product_batch TEXT,
                sentiment TEXT,
                sentiment_method TEXT,
                assignee TEXT,
                reply_message TEXT,
                schema_version INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                log_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                schema_version INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_entity
            ON activity_log (entity_type, entity_id)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            )
        """)
        conn.execute("INSERT OR IGNORE INTO counters (name, value) VALUES ('ticket', 0)")
        conn.execute("INSERT OR IGNORE INTO counters (name, value) VALUES ('log', 0)")


def _next_id(conn, counter_name: str, prefix: str, width: int) -> str:
    """Atomically increment a named counter and return a formatted id,
    e.g. _next_id(conn, 'ticket', 'TCK-', 5) -> 'TCK-00007'."""
    conn.execute(
        "UPDATE counters SET value = value + 1 WHERE name = ?", (counter_name,)
    )
    row = conn.execute(
        "SELECT value FROM counters WHERE name = ?", (counter_name,)
    ).fetchone()
    return f"{prefix}{row['value']:0{width}d}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Sentiment scoring (unchanged from the in-memory version)
# ------------------------------------------------------------------

_ANGRY_WORDS = {
    "dangerous", "disgusting", "furious", "unacceptable", "poison",
    "sick", "ill", "contaminated", "outraged", "horrible", "awful",
}
_FRUSTRATED_WORDS = {
    "frustrating", "frustrated", "annoying", "ridiculous", "irritating",
}
_FRUSTRATED_PHRASES = {"waiting forever", "still not resolved", "still waiting"}
_POSITIVE_WORDS = {"thanks", "great", "love", "appreciate", "happy"}
_POSITIVE_PHRASES = {"thank you"}
_NEGATIONS = {"not", "never", "no", "isnt", "wasnt", "dont", "doesnt", "cant", "wont"}


def _has_unnegated_word(words: set[str], tokens: list[str]) -> bool:
    for i, tok in enumerate(tokens):
        if tok in words:
            window = tokens[max(0, i - 2):i]
            if any(w in _NEGATIONS for w in window):
                continue
            return True
    return False


def score_sentiment(description: str) -> tuple[str, str]:
    text = description.lower().replace("'", "")
    tokens = re.split(r"\W+", text)

    if _has_unnegated_word(_ANGRY_WORDS, tokens):
        return "angry", "keyword_v1"
    if _has_unnegated_word(_FRUSTRATED_WORDS, tokens) or any(
        p in text for p in _FRUSTRATED_PHRASES
    ):
        return "frustrated", "keyword_v1"
    if _has_unnegated_word(_POSITIVE_WORDS, tokens) or any(
        p in text for p in _POSITIVE_PHRASES
    ):
        return "positive", "keyword_v1"
    return "neutral", "keyword_v1"


# ------------------------------------------------------------------
# Row <-> model conversion
# ------------------------------------------------------------------

def _row_to_ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        ticket_id=row["ticket_id"],
        customer_id=row["customer_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        status=row["status"],
        priority=row["priority"],
        issue_type=row["issue_type"],
        subject=row["subject"],
        description=row["description"],
        linked_product_batch=row["linked_product_batch"],
        sentiment=row["sentiment"],
        sentiment_method=row["sentiment_method"],
        assignee=row["assignee"],
        reply_message=row["reply_message"],
        schema_version=row["schema_version"],
    )


def _row_to_log_entry(row: sqlite3.Row) -> ActivityLogEntry:
    return ActivityLogEntry(
        log_id=row["log_id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        activity_type=row["activity_type"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        actor=row["actor"],
        details=json.loads(row["details"]),
        schema_version=row["schema_version"],
    )


_LOGGABLE_FIELDS = {
    "status": "status_changed",
    "priority": "priority_changed",
    "sentiment": "sentiment_scored",
    "assignee": "assigned",
    "reply_message": "replied",
}


def _build_details(
    field: str, old_value, new_value, patch_data: dict, ticket: Ticket
) -> dict:
    if field == "status":
        return {"from": old_value, "to": new_value}
    if field == "priority":
        return {"from": old_value, "to": new_value}
    if field == "sentiment":
        method = patch_data.get("sentiment_method") or ticket.sentiment_method
        return {"sentiment": new_value, "method": method}
    if field == "assignee":
        return {"assignee": new_value}
    if field == "reply_message":
        return {"message": new_value}
    return {}


def _write_log(conn, entity_id: str, activity_type: str, actor: str, details: dict) -> None:
    log_id = _next_id(conn, "log", "LOG-", 6)
    conn.execute(
        """INSERT INTO activity_log
           (log_id, entity_type, entity_id, activity_type, timestamp, actor, details, schema_version)
           VALUES (?, 'ticket', ?, ?, ?, ?, ?, 1)""",
        (log_id, entity_id, activity_type, _now().isoformat(), actor, json.dumps(details)),
    )


# ------------------------------------------------------------------
# Public interface — same function names/signatures as the
# in-memory version, so main.py never needs to change.
# ------------------------------------------------------------------

def create_ticket(data: TicketCreate) -> Ticket:
    sentiment_value, sentiment_method = score_sentiment(data.description)
    now = _now().isoformat()
    with _get_conn() as conn:
        ticket_id = _next_id(conn, "ticket", "TCK-", 5)
        conn.execute(
            """INSERT INTO tickets
               (ticket_id, customer_id, created_at, updated_at, status, priority,
                issue_type, subject, description, linked_product_batch,
                sentiment, sentiment_method, assignee, reply_message, schema_version)
               VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 1)""",
            (
                ticket_id, data.customer_id, now, now, data.priority.value,
                data.issue_type.value, data.subject, data.description,
                data.linked_product_batch, sentiment_value, sentiment_method,
            ),
        )
        _write_log(conn, ticket_id, "created", "system", {})
        _write_log(conn, ticket_id, "sentiment_scored", "system", {
            "sentiment": sentiment_value, "method": sentiment_method,
        })
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return _row_to_ticket(row)


def get_ticket(ticket_id: str) -> Optional[Ticket]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return _row_to_ticket(row) if row else None


def list_tickets(
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    issue_type: Optional[str] = None,
    linked_product_batch: Optional[str] = None,
) -> list[Ticket]:
    query = "SELECT * FROM tickets WHERE 1=1"
    params: list = []
    if customer_id is not None:
        query += " AND customer_id = ?"
        params.append(customer_id)
    if status is not None:
        query += " AND status = ?"
        params.append(status if isinstance(status, str) else status.value)
    if issue_type is not None:
        query += " AND issue_type = ?"
        params.append(issue_type if isinstance(issue_type, str) else issue_type.value)
    if linked_product_batch is not None:
        query += " AND linked_product_batch = ?"
        params.append(linked_product_batch)
    query += " ORDER BY created_at DESC"

    with _get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_ticket(r) for r in rows]


def patch_ticket(ticket_id: str, patch: TicketPatch) -> Optional[Ticket]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if row is None:
            return None
        ticket = _row_to_ticket(row)

        patch_data: dict = patch.model_dump(exclude_unset=True)
        actor: str = patch_data.pop("actor", None) or "system"

        # Normalize enum values to plain strings for comparison/storage
        normalized: dict = {}
        for k, v in patch_data.items():
            normalized[k] = v.value if hasattr(v, "value") else v

        any_changed = False
        set_clauses = []
        set_params = []

        for field, new_value in normalized.items():
            old_value = getattr(ticket, field)
            old_value_cmp = old_value.value if hasattr(old_value, "value") else old_value
            if old_value_cmp == new_value:
                continue
            any_changed = True
            set_clauses.append(f"{field} = ?")
            set_params.append(new_value)

            if field in _LOGGABLE_FIELDS:
                details = _build_details(field, old_value_cmp, new_value, normalized, ticket)
                _write_log(conn, ticket_id, _LOGGABLE_FIELDS[field], actor, details)
            elif field == "sentiment_method":
                old_sentiment_cmp = (
                    ticket.sentiment.value if hasattr(ticket.sentiment, "value")
                    else ticket.sentiment
                )
                sentiment_also_changing = (
                    "sentiment" in normalized
                    and normalized["sentiment"] != old_sentiment_cmp
                )
                if not sentiment_also_changing:
                    _write_log(conn, ticket_id, "sentiment_scored", actor, {
                        "sentiment": ticket.sentiment, "method": new_value,
                    })

        if not any_changed:
            return ticket

        set_clauses.append("updated_at = ?")
        set_params.append(_now().isoformat())
        set_params.append(ticket_id)

        conn.execute(
            f"UPDATE tickets SET {', '.join(set_clauses)} WHERE ticket_id = ?",
            set_params,
        )

        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return _row_to_ticket(row)


def get_activity_log(ticket_id: str) -> list[ActivityLogEntry]:
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM activity_log
               WHERE entity_type = 'ticket' AND entity_id = ?
               ORDER BY timestamp ASC""",
            (ticket_id,),
        ).fetchall()
        return [_row_to_log_entry(r) for r in rows]


# Initialize tables on import so the API works immediately on first request.
init_db()