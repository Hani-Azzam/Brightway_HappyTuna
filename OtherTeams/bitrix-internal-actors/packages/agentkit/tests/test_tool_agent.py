"""EMP-0.3 smoke test: the ReAct loop drives a mock tool end to end with a FakeLlm."""
import json

from packages.agentkit.tests.fakes import AddTool, BoomTool, FakeLlm
from packages.agentkit.tool_agent import ReActConfig, ToolAgent
from packages.agentkit.tool_executor import ToolExecutor


def _make(responses, tool):
    ex = ToolExecutor(max_retries=0)
    ex.register(tool)
    return ToolAgent(FakeLlm(responses), ex), ex


def test_react_loop_calls_tool_then_answers():
    llm_script = [
        json.dumps({"action": "add", "args": {"a": 2, "b": 3}}),
        json.dumps({"action": "final_answer", "answer": "The sum is 5."}),
    ]
    agent, ex = _make(llm_script, AddTool())

    answer = agent.chat("What is 2 + 3?")

    assert answer == "The sum is 5."
    phases = [t.phase for t in ex.get_traces()]
    assert "PLAN" in phases and "ACT" in phases and "OBSERVE" in phases
    # The tool observation was fed back before the final answer.
    assert any("returned: 5" in t.details for t in ex.get_traces())


def test_system_hint_is_injected():
    agent, _ = _make([json.dumps({"action": "final_answer", "answer": "ok"})], AddTool())
    agent._config = ReActConfig(system_hint="You are Dana, a QA employee.")

    agent.chat("hello")

    system_msg = agent._llm.calls[0][0]  # first message of first call
    assert system_msg["role"] == "system"
    assert "Dana, a QA employee" in system_msg["content"]


def test_history_is_passed_as_prior_turns():
    agent, _ = _make([json.dumps({"action": "final_answer", "answer": "ok"})], AddTool())

    agent.chat("now", history=[{"role": "user", "content": "earlier note"}])

    roles = [m["role"] for m in agent._llm.calls[0]]
    assert roles == ["system", "user", "user"]  # system, history turn, current input


def test_invalid_json_triggers_one_repair_then_succeeds():
    agent, _ = _make(
        ["not json at all", json.dumps({"action": "final_answer", "answer": "recovered"})],
        AddTool(),
    )
    assert agent.chat("hi") == "recovered"


def test_tool_exception_is_reported_not_raised():
    agent, ex = _make(
        [
            json.dumps({"action": "boom", "args": {}}),
            json.dumps({"action": "final_answer", "answer": "the tool failed"}),
        ],
        BoomTool(),
    )
    answer = agent.chat("do it")
    assert "failed" in answer.lower()
    assert any("kaboom" in t.details for t in ex.get_traces())
