"""Durable memory: cursors survive restart; episodes recall + dedupe."""
import json

import pytest

from packages.agentkit.tool_executor import ToolExecutor

from services.coordinator.watcher import Coordinator
from services.employee.agent.employee_agent import EmployeeAgent
from services.employee.domain.memory import EmployeeMemory
from services.employee.domain.perception import Perception
from services.employee.personas.persona import load_persona
from services.employee.tests.conftest import PERSONAS_DIR
from services.employee.tools.internal_messaging_adapter import SendChatMessage
from services.employee.worker.activation import EmployeeRuntime, make_activator


class FakeLlm:
    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        # Remember the last prompt so a test can assert on recall content.
        self.last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        return self._responses.pop(0)


@pytest.fixture
def dbs(tmp_path, monkeypatch):
    monkeypatch.setenv("BITRIX_COORD_DB", str(tmp_path / "coord.db"))
    monkeypatch.setenv("BITRIX_EMPLOYEE_DB", str(tmp_path / "emp.db"))


# --- store unit tests ---

def test_cursor_roundtrip_and_survives_restart(dbs):
    EmployeeMemory("EMP-QA-17").set_cursor("CH-1", "42")
    # A fresh instance (a "restart") still sees it — it is durable.
    assert EmployeeMemory("EMP-QA-17").get_cursor("CH-1") == "42"
    assert EmployeeMemory("EMP-QA-17").get_cursor("CH-unknown") is None


def test_episodes_recent_filter_and_has_acted_on(dbs):
    m = EmployeeMemory("EMP-QA-17")
    m.remember("ACTIVATED", ref="e1")
    m.remember("ACTED", ref="send_chat_message", summary="posted report")
    assert m.recent(kind="ACTED")[0]["summary"] == "posted report"
    assert [e["kind"] for e in m.recent()][0] == "ACTED"   # newest first
    assert m.has_acted_on("send_chat_message") is True
    assert m.has_acted_on("nope") is False


# --- integration ---

def _qa_runtime(llm, chat_http, chat_client) -> EmployeeRuntime:
    persona = load_persona(PERSONAS_DIR / "qa_employee.yaml")
    memory = EmployeeMemory(persona.employee_id)
    executor = ToolExecutor(max_retries=0)
    executor.register(SendChatMessage(http=chat_http, employee_id=persona.employee_id))
    agent = EmployeeAgent(llm, executor, persona)
    perception = Perception(chat_client(persona.employee_id), cursors=memory)  # durable cursors
    return EmployeeRuntime(agent=agent, perception=perception, memory=memory, executor=executor)


def test_durable_cursor_prevents_re_observing_after_restart(chat_service, chat_client, dbs):
    ch = chat_service.create_channel("COO-1", "incident", ["EMP-QA-17"], name="ht")
    cid = ch.channel
    chat_service.send_message("COO-1", cid, "first message")

    p1 = Perception(chat_client("EMP-QA-17"), cursors=EmployeeMemory("EMP-QA-17"))
    assert len(p1.gather().observations) == 1        # sees the message once

    # "Restart": brand-new perception + memory instance, same employee/db.
    p2 = Perception(chat_client("EMP-QA-17"), cursors=EmployeeMemory("EMP-QA-17"))
    assert p2.gather().is_empty()                    # cursor was durable -> nothing re-observed


def test_action_is_recorded_and_recalled(chat_service, chat_http, chat_client, coord_reader, dbs):
    ch = chat_service.create_channel("COO-1", "incident", ["EMP-QA-17"], name="ht")
    cid = ch.channel
    chat_service.send_message("COO-1", cid, "please report @EMP-QA-17")

    llm = FakeLlm([
        json.dumps({"action": "send_chat_message",
                    "args": {"channel": cid, "body": "LAB-781 POSITIVE @COO-1"}}),
        json.dumps({"action": "final_answer", "answer": "Reported."}),
    ])
    runtime = _qa_runtime(llm, chat_http, chat_client)
    Coordinator(activate=make_activator({"EMP-QA-17": runtime}), reader=coord_reader).poll_once()

    acted = runtime.memory.recent(kind="ACTED")
    assert len(acted) == 1 and "send_chat_message" in acted[0]["ref"]


def test_recall_is_injected_into_prompt_on_second_activation(
    chat_service, chat_http, chat_client, coord_reader, dbs
):
    ch = chat_service.create_channel("COO-1", "incident", ["EMP-QA-17"], name="ht")
    cid = ch.channel

    # First activation: COO asks, employee reports.
    chat_service.send_message("COO-1", cid, "report status @EMP-QA-17")
    llm = FakeLlm([
        json.dumps({"action": "send_chat_message",
                    "args": {"channel": cid, "body": "LAB-781 POSITIVE @COO-1"}}),
        json.dumps({"action": "final_answer", "answer": "Reported."}),
    ])
    runtime = _qa_runtime(llm, chat_http, chat_client)
    coord = Coordinator(activate=make_activator({"EMP-QA-17": runtime}), reader=coord_reader)
    coord.poll_once()

    # Second activation: the recall block must now carry the earlier action so the
    # employee can choose not to repeat it.
    chat_service.send_message("COO-1", cid, "any update @EMP-QA-17")
    runtime.agent._llm._responses = [   # reuse the same FakeLlm, new script
        json.dumps({"action": "final_answer", "answer": "Already reported; nothing new."}),
    ]
    coord.poll_once()
    assert "ALREADY DONE" in runtime.agent._llm.last_user
    # Still exactly one report in the channel — no duplicate.
    reports = [m for m in chat_service.read_channel("COO-1", cid).messages
               if m.sender == "EMP-QA-17" and "LAB-781" in m.body]
    assert len(reports) == 1
