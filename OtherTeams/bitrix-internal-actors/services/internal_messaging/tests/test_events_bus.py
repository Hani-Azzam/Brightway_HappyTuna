"""P4 — event bus: per-recipient fan-out, body excluded, isolation by construction."""
from __future__ import annotations

import pytest

from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.domain.store import Store
from services.internal_messaging.integration.clock import FixedClock
from services.internal_messaging.integration.events import BusPublisher, InMemoryBus
from services.internal_messaging.integration.ids import SeededIdFactory
from services.internal_messaging.integration.identity import Registry


@pytest.fixture
def bus() -> InMemoryBus:
    return InMemoryBus()


@pytest.fixture
def service(db_path, registry, bus) -> InternalMessagingService:
    store = Store(db_path, FixedClock(), SeededIdFactory(seed=1))
    return InternalMessagingService(store, registry, BusPublisher(bus))


def test_event_fans_out_to_each_member_inbox(service, bus):
    ch = service.create_channel(
        caller_id="COO-1", channel_type="incident", members=["EMP-QA-17"],
        correlation_id="HT-2026-001",
    ).channel
    service.send_message(caller_id="EMP-QA-17", channel=ch, body="Line 4 halted @COO-1")

    assert "chat.inbox.COO-1" in bus.published
    assert "chat.inbox.EMP-QA-17" in bus.published
    assert "chat.message_posted" in bus.published        # global stream for the Director
    assert "chat.inbox.CEO-1" not in bus.published        # non-member never notified


def test_event_payload_excludes_body_but_carries_refs(service, bus):
    ch = service.create_channel(
        caller_id="COO-1", channel_type="incident", members=["EMP-QA-17"]
    ).channel
    service.send_message(caller_id="EMP-QA-17", channel=ch, body="secret contents @COO-1")

    payload = bus.published["chat.inbox.COO-1"][0]
    assert "body" not in payload                          # content plane vs event plane
    assert payload["message_id"].startswith("msg_")
    assert payload["mentions"] == ["COO-1"]
    assert set(payload["recipients"]) == {"COO-1", "EMP-QA-17"}
    assert payload["event_type"] == "chat.message_posted"
