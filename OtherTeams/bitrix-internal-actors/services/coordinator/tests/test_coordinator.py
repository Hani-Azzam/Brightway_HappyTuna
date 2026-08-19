"""Coordinator end-to-end against a real internal_messaging service + activation log."""
import pytest

from services.coordinator import activation_store
from services.coordinator.events import ActivationEvent
from services.coordinator.reader import ServiceMessageReader
from services.coordinator.watcher import Coordinator
from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.domain.store import Store
from services.internal_messaging.integration.clock import FixedClock
from services.internal_messaging.integration.ids import SeededIdFactory
from services.internal_messaging.integration.identity import Registry


@pytest.fixture
def service(tmp_path, monkeypatch) -> InternalMessagingService:
    monkeypatch.setenv("BITRIX_COORD_DB", str(tmp_path / "coord.db"))
    store = Store(str(tmp_path / "chat.db"), FixedClock(), SeededIdFactory(seed=1))
    registry = Registry({"COO-1": "coo", "EMP-QA-17": "employee", "COORD-1": "coordinator"})
    return InternalMessagingService(store, registry)


@pytest.fixture
def reader(service) -> ServiceMessageReader:
    return ServiceMessageReader(service, "COORD-1")


def test_employee_post_activates_coo_and_logs(service, reader):
    ch = service.create_channel(
        "COO-1", "incident", ["EMP-QA-17"], name="ht", correlation_id="HT-2026-001"
    )
    service.send_message("EMP-QA-17", ch.channel, "Salmonella suspected on Line 4 @COO-1")

    woken: list[str] = []
    coord = Coordinator(activate=lambda agent_id, ev: woken.append(agent_id), reader=reader)
    fired = coord.poll_once()

    assert woken == ["COO-1"]                       # the crisis chain: COO auto-activated
    assert [a for a, _ in fired] == ["COO-1"]
    log = activation_store.list_all()
    assert len(log) == 1
    assert log[0]["agent_id"] == "COO-1"
    assert log[0]["correlation_id"] == "HT-2026-001"
    assert log[0]["event_kind"] == "CHAT_MESSAGE"


def test_poll_is_incremental_no_duplicate_activation(service, reader):
    ch = service.create_channel("COO-1", "group", ["EMP-QA-17"], name="x")
    service.send_message("EMP-QA-17", ch.channel, "first @COO-1")

    coord = Coordinator(activate=lambda agent_id, ev: None, reader=reader)
    assert len(coord.poll_once()) == 1
    assert coord.poll_once() == []                  # nothing new -> no re-activation

    service.send_message("EMP-QA-17", ch.channel, "second @COO-1")
    assert len(coord.poll_once()) == 1              # only the new message fires


def test_own_mention_does_not_wake_sender(service, reader):
    ch = service.create_channel("COO-1", "group", ["EMP-QA-17"], name="x")
    service.send_message("EMP-QA-17", ch.channel, "note @EMP-QA-17 and @COO-1")

    woken: list[str] = []
    Coordinator(activate=lambda agent_id, ev: woken.append(agent_id), reader=reader).poll_once()
    assert woken == ["COO-1"]


def test_scenario_event_via_submit(service, reader):
    woken: list[str] = []
    coord = Coordinator(activate=lambda agent_id, ev: woken.append(agent_id), reader=reader)
    coord.submit(ActivationEvent(kind="SCENARIO_EVENT", source="scenario", name="SUSPICIOUS_SAMPLE"))

    assert woken == ["EMP-QA-17", "COO-1"]
    assert len(activation_store.list_all()) == 2
