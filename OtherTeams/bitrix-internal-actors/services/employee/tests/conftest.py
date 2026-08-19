"""Shared fixtures for the employee tests.

The employee now reaches chat through the Internal Messaging System (v2) over REST.
These fixtures stand up a real v2 service on a temp SQLite store and expose it three
ways: an in-process `chat_service` (for seeding + the coordinator's system read), a
`TestClient` (`chat_http`) that the employee's REST tools/clients talk to, and
factory fixtures that bind an identity to that transport. No network, no real model.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.coordinator.reader import ServiceMessageReader
from services.employee.tools.internal_messaging_client import InternalMessagingClient
from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.domain.store import Store
from services.internal_messaging.integration.clock import FixedClock
from services.internal_messaging.integration.ids import SeededIdFactory
from services.internal_messaging.integration.identity import Registry
from services.internal_messaging.transport.rest.app import create_rest_app

PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"


@pytest.fixture
def chat_service(tmp_path) -> InternalMessagingService:
    store = Store(str(tmp_path / "chat.db"), FixedClock(), SeededIdFactory(seed=1))
    registry = Registry(
        {
            "COO-1": "coo",
            "CEO-1": "ceo",
            "EMP-QA-17": "employee",
            "EXT-9": "employee",
            "COORD-1": "coordinator",   # -> chat:system (the activation firehose)
        }
    )
    return InternalMessagingService(store, registry)


@pytest.fixture
def chat_http(chat_service) -> TestClient:
    return TestClient(create_rest_app(chat_service))


@pytest.fixture
def chat_client(chat_http):
    """Factory: an identity-bound REST read client for perception."""
    def make(agent_id: str) -> InternalMessagingClient:
        return InternalMessagingClient(http=chat_http, agent_id=agent_id)

    return make


@pytest.fixture
def coord_reader(chat_service) -> ServiceMessageReader:
    return ServiceMessageReader(chat_service, "COORD-1")
