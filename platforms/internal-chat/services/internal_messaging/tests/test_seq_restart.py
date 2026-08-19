"""Regression: `seq` must stay monotonic across a service restart.

`seq` is derived from the DB (max+1), not an in-process counter — otherwise a
restarted service would reset it to 1, collide with existing rows, and break the
`since` cursor (a new message would not be > the reader's stored cursor, so it
would never be seen as new)."""
from __future__ import annotations

from services.internal_messaging.domain.store import SqliteStore
from services.internal_messaging.integration.clock import FixedClock
from services.internal_messaging.integration.ids import UuidFactory


def test_seq_keeps_climbing_across_restart(tmp_path):
    db = str(tmp_path / "chat.db")

    s1 = SqliteStore(db, FixedClock(), UuidFactory())
    ch = s1.create_channel("group", "g", None, "COO-1", ["EMP-QA-17"])
    m1 = s1.add_message(ch["id"], "COO-1", "first", "internal", "internal", [], None)

    # "Restart": brand-new store on the same DB file, fresh in-process id factory
    # (its own seq counter starts at 0 again).
    s2 = SqliteStore(db, FixedClock(), UuidFactory())
    m2 = s2.add_message(ch["id"], "EMP-QA-17", "second", "internal", "internal", [], None)

    assert m2["seq"] > m1["seq"]          # would be equal with an in-process counter
    # The firehose still sees the post-restart message as strictly newer.
    newer = s2.all_messages_since(m1["seq"])
    assert [m["id"] for m in newer] == [m2["id"]]
