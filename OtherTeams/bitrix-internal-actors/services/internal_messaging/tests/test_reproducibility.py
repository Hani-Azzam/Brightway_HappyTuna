"""Reproducibility — same seed + fixed clock ⇒ identical ids, seq, timestamps."""
from __future__ import annotations

from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.domain.store import Store
from services.internal_messaging.integration.clock import FixedClock
from services.internal_messaging.integration.ids import SeededIdFactory
from services.internal_messaging.integration.identity import Registry


def _run(db_path: str) -> list[tuple]:
    store = Store(db_path, FixedClock(), SeededIdFactory(seed=42))
    svc = InternalMessagingService(store, Registry({"COO-1": "coo", "EMP-QA-17": "employee"}))
    ch = svc.create_channel(caller_id="COO-1", channel_type="incident", members=["EMP-QA-17"])
    svc.send_message(caller_id="EMP-QA-17", channel=ch.channel, body="one @COO-1")
    svc.send_message(caller_id="COO-1", channel=ch.channel, body="two")
    history = svc.read_channel(caller_id="COO-1", channel=ch.channel)
    return [(m.message_id, m.seq, m.sent_at.isoformat()) for m in history.messages]


def test_two_seeded_runs_are_identical(tmp_path):
    run_a = _run(str(tmp_path / "a.db"))
    run_b = _run(str(tmp_path / "b.db"))
    assert run_a == run_b
    # and ids are the deterministic, greppable form
    assert run_a[0][0].startswith("msg_42")
