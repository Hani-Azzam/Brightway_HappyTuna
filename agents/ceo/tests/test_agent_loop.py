"""Unit tests for CeoAgent's step loop. No network, no Docker, no MCP servers.

    pytest ceo_agent/tests/test_agent_loop.py

These cover step accounting: what the loop records about a step versus what
actually happened in it. Three consecutive smoke runs were reported as failures
("maximum retries exceeded") for steps whose tool call had returned real data,
and the CEO's final report then described an information vacuum over the top of
results it had been handed. Everything here is about that record being true.
"""

from __future__ import annotations

import json

from agents.CEO_Agent import CeoAgent, CeoConfig
from base.tool_base import ToolBase, ToolResult, ToolSchema
from services.tool_executor import ToolExecutor

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeLlm:
    """Replays queued raw responses and keeps every prompt it was sent."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[list] = []

    def invoke(self, messages: list) -> str:
        self.prompts.append(list(messages))
        if not self._responses:
            raise AssertionError("FakeLlm ran out of queued responses.")
        return self._responses.pop(0)

    @property
    def last_prompt_text(self) -> str:
        return "\n".join(str(m.content) for m in self.prompts[-1])


class FakeTool(ToolBase):
    """A tool with a scripted outcome that counts how often it was run."""

    def __init__(self, name: str, result: ToolResult, required: list[str] | None = None) -> None:
        self._name = name
        self._result = result
        self._required = required or []
        self.calls: list[dict] = []

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self._name,
            description=f"{self._name} description",
            parameters={
                "type": "object",
                "properties": {k: {"type": "string"} for k in self._required},
                "required": list(self._required),
            },
        )

    def run(self, **kwargs) -> ToolResult:
        self.calls.append(kwargs)
        return self._result


CHANNELS = [{"id": "C-8821", "name": "General"}, {"id": "C-9014", "name": "Ops"}]

PLAN = json.dumps({"plan": ["List the internal channels", "Read the main channel"]})
ONE_STEP_PLAN = json.dumps({"plan": ["List the internal channels"]})
SUMMARY = "Final report."


def build_agent(llm: FakeLlm, tools: list[FakeTool], retries: int = 3):
    executor = ToolExecutor(max_retries=0, base_delay=0.0)
    for t in tools:
        executor.register(t)
    agent = CeoAgent(llm, executor, CeoConfig(max_tool_retries_per_step=retries))
    return agent, executor


def outcome_traces(executor: ToolExecutor) -> list:
    return [t for t in executor.get_traces() if t.phase.startswith("STEP_")]


# ---------------------------------------------------------------------------
# A successful call is a completed step
# ---------------------------------------------------------------------------


def test_successful_call_completes_the_step_without_a_step_complete_reply():
    """The run-3 shape: the call returned the channels, the model never emitted
    step_complete, and the step was recorded as a failure."""
    tool = FakeTool("chat.list_channels", ToolResult(value=CHANNELS))
    llm = FakeLlm([
        ONE_STEP_PLAN,
        json.dumps({"action": "chat.list_channels", "args": {}}),
        SUMMARY,
    ])
    agent, executor = build_agent(llm, [tool])

    agent.chat("A crisis")

    (step_trace,) = outcome_traces(executor)
    assert step_trace.phase == "STEP_COMPLETE"
    assert "maximum retries exceeded" not in step_trace.details
    assert "did not complete" not in step_trace.details


def test_the_returned_data_travels_with_the_outcome():
    """The channels were "sitting in the step's own result" -- so the final
    report must be handed them, not just a summary sentence about them."""
    tool = FakeTool("chat.list_channels", ToolResult(value=CHANNELS))
    llm = FakeLlm([
        ONE_STEP_PLAN,
        json.dumps({"action": "chat.list_channels", "args": {}}),
        SUMMARY,
    ])
    agent, executor = build_agent(llm, [tool])

    agent.chat("A crisis")

    summary_prompt = llm.last_prompt_text
    assert "C-8821" in summary_prompt
    assert '"completed": true' in summary_prompt.lower()


def test_an_empty_but_correct_result_still_completes_the_step():
    """Run 2: list_tickets came back {"count": 0}. Nothing to report is a
    successful read, not a failed one."""
    tool = FakeTool("support.list_tickets", ToolResult(value={"count": 0, "tickets": []}))
    llm = FakeLlm([
        ONE_STEP_PLAN,
        json.dumps({"action": "support.list_tickets", "args": {}}),
        SUMMARY,
    ])
    agent, executor = build_agent(llm, [tool])

    agent.chat("A crisis")

    (step_trace,) = outcome_traces(executor)
    assert step_trace.phase == "STEP_COMPLETE"
    assert '"count": 0' in step_trace.details


def test_a_side_effecting_tool_is_not_called_twice_for_one_step():
    """Run 1: create_post returned a real post id. Continuing the retry loop
    past that would post again."""
    tool = FakeTool("social.create_post", ToolResult(value={"post_id": "P-4471"}))
    llm = FakeLlm([
        ONE_STEP_PLAN,
        json.dumps({"action": "social.create_post", "args": {"text": "statement"}}),
        SUMMARY,
    ])
    agent, _ = build_agent(llm, [tool], retries=6)

    agent.chat("A crisis")

    assert len(tool.calls) == 1


# ---------------------------------------------------------------------------
# A step that really did not finish says why
# ---------------------------------------------------------------------------


def test_failing_tool_calls_are_reported_as_the_step_not_completing():
    tool = FakeTool("chat.list_channels", ToolResult(error="server unreachable"))
    llm = FakeLlm([
        ONE_STEP_PLAN,
        json.dumps({"action": "chat.list_channels", "args": {}}),
        json.dumps({"action": "chat.list_channels", "args": {}}),
        SUMMARY,
    ])
    agent, executor = build_agent(llm, [tool], retries=2)

    agent.chat("A crisis")

    (step_trace,) = outcome_traces(executor)
    assert step_trace.phase == "STEP_INCOMPLETE"
    assert "server unreachable" in step_trace.details


def test_unusable_replies_are_named_as_such_not_as_a_tool_failure():
    """The other half of the conflation: the model never produced a runnable
    action. No tool failed, because no tool was called."""
    llm = FakeLlm([
        ONE_STEP_PLAN,
        "I think we should probably look at the channels first.",
        "Let me consider the options.",
        SUMMARY,
    ])
    agent, executor = build_agent(llm, [FakeTool("chat.list_channels", ToolResult(value=CHANNELS))], retries=2)

    agent.chat("A crisis")

    (step_trace,) = outcome_traces(executor)
    assert step_trace.phase == "STEP_INCOMPLETE"
    assert "no usable action" in step_trace.details
    assert "tool call(s) were attempted" not in step_trace.details


def test_step_complete_after_only_failures_records_that_nothing_succeeded():
    """The model can claim the step is done; the record still shows the calls
    that failed underneath the claim."""
    tool = FakeTool("chat.list_channels", ToolResult(error="server unreachable"))
    llm = FakeLlm([
        ONE_STEP_PLAN,
        json.dumps({"action": "chat.list_channels", "args": {}}),
        json.dumps({"action": "step_complete", "result": "Channels reviewed."}),
        SUMMARY,
    ])
    agent, executor = build_agent(llm, [tool], retries=3)

    agent.chat("A crisis")

    (step_trace,) = outcome_traces(executor)
    assert "No tool call succeeded" in step_trace.details
    assert "server unreachable" in step_trace.details


# ---------------------------------------------------------------------------
# Ids from earlier steps
# ---------------------------------------------------------------------------


def test_the_next_step_is_shown_the_ids_the_previous_step_returned():
    """The planner wrote channel='General' -- a name it invented -- one step
    after the real ids had come back. They have to be in front of it."""
    lister = FakeTool("chat.list_channels", ToolResult(value=CHANNELS))
    reader = FakeTool("chat.read_channel", ToolResult(value={"messages": []}), required=["channel"])
    llm = FakeLlm([
        PLAN,
        json.dumps({"action": "chat.list_channels", "args": {}}),
        json.dumps({"action": "chat.read_channel", "args": {"channel": "C-8821"}}),
        SUMMARY,
    ])
    agent, _ = build_agent(llm, [lister, reader])

    agent.chat("A crisis")

    # The prompt for step 2 is the one sent before the read_channel reply.
    step_two_prompt = "\n".join(str(m.content) for m in llm.prompts[2])
    assert "C-8821" in step_two_prompt
    assert "copied EXACTLY" in step_two_prompt
