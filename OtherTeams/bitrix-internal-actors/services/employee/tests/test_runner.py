"""The assembler: build_population wires each persona with authority-guarded tools,
and run() embeds the coordinator and drives activations end-to-end."""
import json

import pytest

from services.coordinator.watcher import Coordinator
from services.employee.app.config import Settings
from services.employee.domain.authority import AuthorizedTool
from services.employee.worker.activation import make_activator
from services.employee.worker.runner import build_population, run


class FakeLlm:
    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        return self._responses.pop(0)


def _settings() -> Settings:
    # Empty base_url -> the REST tools emit relative paths the TestClient resolves.
    return Settings(internal_messaging_url="")


def test_build_population_wires_authority_guarded_tools(chat_http, tmp_path, monkeypatch):
    monkeypatch.setenv("BITRIX_EMPLOYEE_DB", str(tmp_path / "emp.db"))
    runtimes, _ = build_population(
        _settings(), llm_factory=lambda p: FakeLlm([]), chat_http=chat_http
    )

    assert "EMP-QA-17" in runtimes
    executor = runtimes["EMP-QA-17"].executor
    # QA persona allows internal_messaging + mail + portal -> one tool each.
    assert {s["name"] for s in executor.tool_schemas()} == {
        "send_chat_message", "send_mail", "update_task"
    }
    # Every registered tool is wrapped in the authority guard (enforced in code).
    assert all(isinstance(t, AuthorizedTool) for t in executor._registry.values())


def test_build_population_loads_all_personas_with_scoped_tools(chat_http, tmp_path, monkeypatch):
    monkeypatch.setenv("BITRIX_EMPLOYEE_DB", str(tmp_path / "emp.db"))
    runtimes, _ = build_population(
        _settings(), llm_factory=lambda p: FakeLlm([]), chat_http=chat_http
    )

    assert set(runtimes) == {
        "EMP-QA-17", "PROD-WORKER-3", "PLANT-MGR-1", "CONCERNED-EMP-1", "WHISTLEBLOWER-1",
    }

    def tool_names(agent_id: str) -> set[str]:
        return {s["name"] for s in runtimes[agent_id].executor.tool_schemas()}

    # Tools are scoped to each persona's authorized channels (capability gate).
    assert tool_names("PROD-WORKER-3") == {"send_chat_message", "update_task"}   # no mail
    # The whistleblower's `social` channel has no tool yet, so it's simply absent.
    assert tool_names("WHISTLEBLOWER-1") == {"send_chat_message", "send_mail", "update_task"}


def test_population_activation_end_to_end(
    chat_service, chat_http, coord_reader, tmp_path, monkeypatch
):
    monkeypatch.setenv("BITRIX_EMPLOYEE_DB", str(tmp_path / "emp.db"))
    monkeypatch.setenv("BITRIX_COORD_DB", str(tmp_path / "coord.db"))

    ch = chat_service.create_channel(
        "COO-1", "incident", ["EMP-QA-17"], name="ht", correlation_id="HT-1"
    )
    cid = ch.channel
    chat_service.send_message("COO-1", cid, "status update please @EMP-QA-17")

    def fake_llm(_persona):
        return FakeLlm([
            json.dumps({"action": "send_chat_message",
                        "args": {"channel": cid, "body": "On it — sampling underway."}}),
            json.dumps({"action": "final_answer", "answer": "Replied."}),
        ])

    runtimes, _ = build_population(_settings(), llm_factory=fake_llm, chat_http=chat_http)
    Coordinator(activate=make_activator(runtimes), reader=coord_reader).poll_once()

    replies = [m for m in chat_service.read_channel("COO-1", cid).messages
               if m.sender == "EMP-QA-17"]
    assert any("sampling underway" in m.body for m in replies)


def test_run_polls_the_firehose_then_stops(chat_http, tmp_path, monkeypatch):
    monkeypatch.setenv("BITRIX_EMPLOYEE_DB", str(tmp_path / "emp.db"))

    class FakeReader:
        def __init__(self):
            self.calls = 0

        def all_messages_since(self, since):
            self.calls += 1
            return []

    reader = FakeReader()
    run(_settings(), reader=reader, llm_factory=lambda p: FakeLlm([]),
        chat_http=chat_http, interval=0, max_polls=3)
    assert reader.calls == 3


def test_run_end_to_end_via_rest_firehose(chat_service, chat_http, tmp_path, monkeypatch):
    """The real deployment path: run() -> RestMessageReader over /api/messages ->
    activate -> perceive -> authority-guarded post lands back in the channel."""
    from services.coordinator.reader import RestMessageReader

    monkeypatch.setenv("BITRIX_EMPLOYEE_DB", str(tmp_path / "emp.db"))
    monkeypatch.setenv("BITRIX_COORD_DB", str(tmp_path / "coord.db"))
    ch = chat_service.create_channel(
        "COO-1", "incident", ["EMP-QA-17"], name="ht", correlation_id="HT-2"
    )
    cid = ch.channel
    chat_service.send_message("COO-1", cid, "please report @EMP-QA-17")

    def fake_llm(_persona):
        return FakeLlm([
            json.dumps({"action": "send_chat_message",
                        "args": {"channel": cid, "body": "Reporting now."}}),
            json.dumps({"action": "final_answer", "answer": "done"}),
        ])

    reader = RestMessageReader(chat_http, "", "COORD-1")   # firehose over the REST route
    run(_settings(), reader=reader, llm_factory=fake_llm, chat_http=chat_http,
        interval=0, max_polls=1)

    replies = [m for m in chat_service.read_channel("COO-1", cid).messages
               if m.sender == "EMP-QA-17"]
    assert any("Reporting now." in m.body for m in replies)
