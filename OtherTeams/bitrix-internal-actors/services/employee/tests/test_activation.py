"""The full chain: coordinator activates an employee, who then perceives and acts.

Fully mocked LLM + a real v2 chat service (over REST) + real coordinator. No network."""
import json

import pytest

from packages.agentkit.tool_executor import ToolExecutor

from services.coordinator.events import ActivationEvent
from services.coordinator.watcher import Coordinator
from services.employee.agent.employee_agent import EmployeeAgent
from services.employee.domain.perception import Perception
from services.employee.personas.persona import load_persona
from services.employee.tests.conftest import PERSONAS_DIR
from services.employee.tools.internal_messaging_adapter import SendChatMessage
from services.employee.worker.activation import EmployeeRuntime, make_activator


class FakeLlm:
    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        return self._responses.pop(0)


@pytest.fixture
def coord_db(tmp_path, monkeypatch):
    monkeypatch.setenv("BITRIX_COORD_DB", str(tmp_path / "coord.db"))


def _qa_runtime(llm, chat_http, chat_client) -> EmployeeRuntime:
    persona = load_persona(PERSONAS_DIR / "qa_employee.yaml")
    executor = ToolExecutor(max_retries=0)
    executor.register(SendChatMessage(http=chat_http, employee_id=persona.employee_id))
    agent = EmployeeAgent(llm, executor, persona)
    return EmployeeRuntime(agent=agent, perception=Perception(chat_client(persona.employee_id)))


def test_mention_activates_employee_who_then_replies(
    chat_service, chat_http, chat_client, coord_reader, coord_db
):
    ch = chat_service.create_channel(
        "COO-1", "incident", ["EMP-QA-17"], name="ht", correlation_id="HT-2026-001"
    )
    cid = ch.channel
    # The COO asks the QA employee for a status update.
    chat_service.send_message("COO-1", cid, "status update please @EMP-QA-17")

    # The employee's scripted reasoning: post a reply, then finish.
    llm = FakeLlm([
        json.dumps({"action": "send_chat_message",
                    "args": {"channel": cid,
                             "body": "On it — Line 4 halted, sampling underway."}}),
        json.dumps({"action": "final_answer", "answer": "Replied to the COO."}),
    ])
    runtimes = {"EMP-QA-17": _qa_runtime(llm, chat_http, chat_client)}

    coord = Coordinator(activate=make_activator(runtimes), reader=coord_reader)
    coord.poll_once()      # coordinator sees the mention -> activates EMP-QA-17 -> it acts

    replies = [m for m in chat_service.read_channel("COO-1", cid).messages
               if m.sender == "EMP-QA-17"]
    assert any("Line 4 halted" in m.body for m in replies)


def test_activation_for_unknown_agent_is_ignored(chat_service, coord_reader, coord_db):
    """A mention of an agent we don't run here (e.g. the COO) must not crash."""
    ch = chat_service.create_channel("COO-1", "group", ["EMP-QA-17"], name="x")
    chat_service.send_message("EMP-QA-17", ch.channel, "over to you @COO-1")

    coord = Coordinator(activate=make_activator({}), reader=coord_reader)  # no runtimes
    coord.poll_once()                                  # should be a no-op, not an error


def test_employee_with_nothing_new_does_not_act(chat_service, chat_http, chat_client):
    """Activated but no unseen observations -> no LLM call, no post."""
    ch = chat_service.create_channel("COO-1", "group", ["EMP-QA-17"], name="x")
    llm = FakeLlm([])  # would IndexError if the loop tried to run
    runtime = _qa_runtime(llm, chat_http, chat_client)
    # Perceive once so the cursor is caught up (nothing new remains).
    runtime.perception.gather()

    event = ActivationEvent(kind="CHAT_MESSAGE", source="internal_messaging",
                            channel_id=ch.channel, actor_id="COO-1", mentions=["EMP-QA-17"])
    assert runtime.activate(event) is None


class _RaisingLlm:
    """Stands in for an LLM that errors (e.g. Anthropic 429 rate_limit_error)."""
    def invoke(self, messages):
        raise RuntimeError("LLM unavailable (429)")


def test_failed_cycle_does_not_crash_the_worker(
    chat_service, chat_http, chat_client, coord_reader, coord_db
):
    ch = chat_service.create_channel("COO-1", "incident", ["EMP-QA-17"], name="ht")
    chat_service.send_message("COO-1", ch.channel, "report status @EMP-QA-17")

    runtime = _qa_runtime(_RaisingLlm(), chat_http, chat_client)
    coord = Coordinator(activate=make_activator({"EMP-QA-17": runtime}), reader=coord_reader)

    fired = coord.poll_once()          # must NOT raise despite the LLM error
    assert [a for a, _ in fired] == ["EMP-QA-17"]   # activated, then failed gracefully
