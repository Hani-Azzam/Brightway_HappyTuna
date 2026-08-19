"""EMP-1 slice: a persona-driven agent posts to the Internal Messaging System (v2).

FakeLlm plays the QA employee's reasoning (call send_chat_message, then finish);
a real v2 service over REST (temp SQLite) plays chat. No network, no real model.
"""
import json

from packages.agentkit.tool_executor import ToolExecutor

from services.employee.agent.employee_agent import EmployeeAgent
from services.employee.personas.persona import load_persona
from services.employee.tests.conftest import PERSONAS_DIR
from services.employee.tools.internal_messaging_adapter import SendChatMessage


class FakeLlm:
    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        return self._responses.pop(0)


def test_qa_persona_posts_via_react_loop(chat_service, chat_http):
    persona = load_persona(PERSONAS_DIR / "qa_employee.yaml")
    ch = chat_service.create_channel("COO-1", "incident", [persona.employee_id], name="ht")
    cid = ch.channel

    llm = FakeLlm([
        json.dumps({"action": "send_chat_message",
                    "args": {"channel": cid,
                             "body": "LAB-781 POSITIVE for salmonella on Line 4 @COO-1"}}),
        json.dumps({"action": "final_answer", "answer": "Reported to the incident channel."}),
    ])
    ex = ToolExecutor(max_retries=0)
    ex.register(SendChatMessage(http=chat_http, employee_id=persona.employee_id))
    agent = EmployeeAgent(llm, ex, persona)

    answer = agent.chat("Handle the LAB-781 result.")

    assert answer == "Reported to the incident channel."
    posted = chat_service.read_channel("COO-1", cid).messages
    assert len(posted) == 1
    assert "salmonella" in posted[0].body
    assert agent.employee_id == "EMP-QA-17"
