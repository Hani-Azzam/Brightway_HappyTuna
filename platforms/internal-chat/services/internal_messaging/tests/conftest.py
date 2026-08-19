from __future__ import annotations

import pytest

from packages.mcp_core import ToolContext
from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.domain.store import Store
from services.internal_messaging.integration.clock import FixedClock
from services.internal_messaging.integration.events import RecordingPublisher
from services.internal_messaging.integration.ids import SeededIdFactory
from services.internal_messaging.integration.identity import Registry


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "chat.db")


@pytest.fixture
def registry() -> Registry:
    return Registry(
        {
            "COO-1": "coo",
            "CEO-1": "ceo",
            "EMP-QA-17": "employee",
            "OUTSIDER-1": "employee",
        }
    )


@pytest.fixture
def publisher() -> RecordingPublisher:
    return RecordingPublisher()


@pytest.fixture
def store(db_path) -> Store:
    return Store(db_path, FixedClock(), SeededIdFactory(seed=1))


@pytest.fixture
def service(store, registry, publisher) -> InternalMessagingService:
    return InternalMessagingService(store, registry, publisher)


@pytest.fixture
def ctx():
    def make(caller_id: str, role: str = "employee") -> ToolContext:
        return ToolContext(caller_id=caller_id, caller_role=role)

    return make


@pytest.fixture
def incident(service):
    """A ready incident channel: COO owner, EMP-QA-17 member. Returns its id."""
    receipt = service.create_channel(
        caller_id="COO-1",
        channel_type="incident",
        members=["EMP-QA-17"],
        name="ht-crisis",
        correlation_id="HT-2026-001",
    )
    return receipt.channel
