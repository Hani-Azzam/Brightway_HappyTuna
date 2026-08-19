"""Unit tests for the tool executor: validation, retries, idempotency."""
from packages.agentkit.tests.fakes import AddTool
from packages.agentkit.tool_base import ToolBase, ToolResult, ToolSchema
from packages.agentkit.tool_executor import ToolExecutor


def test_unknown_tool_returns_error_without_running():
    ex = ToolExecutor()
    result = ex.execute(1, "nope", {})
    assert not result.ok
    assert "Unknown tool" in result.error


def test_missing_required_arg_is_rejected():
    ex = ToolExecutor()
    ex.register(AddTool())
    result = ex.execute(1, "add", {"a": 1})
    assert not result.ok
    assert "Missing required arguments" in result.error


def test_happy_path_returns_value_and_traces():
    ex = ToolExecutor()
    ex.register(AddTool())
    result = ex.execute(1, "add", {"a": 4, "b": 6})
    assert result.ok and result.value == 10
    assert ex.get_traces()[-1].phase == "ACT"


class _FlakyTool(ToolBase):
    def __init__(self, idempotent: bool) -> None:
        self.attempts = 0
        self._idempotent = idempotent

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema("flaky", "fails first, then succeeds",
                          {"type": "object", "required": [], "properties": {}})

    def run(self) -> ToolResult:
        self.attempts += 1
        if self.attempts == 1:
            return ToolResult(error="transient", is_idempotent=self._idempotent)
        return ToolResult(value="ok", is_idempotent=self._idempotent)


def test_idempotent_tool_is_retried():
    tool = _FlakyTool(idempotent=True)
    ex = ToolExecutor(max_retries=2, base_delay=0.0)
    ex.register(tool)
    result = ex.execute(1, "flaky", {})
    assert result.ok and tool.attempts == 2


def test_non_idempotent_tool_runs_once():
    tool = _FlakyTool(idempotent=False)
    ex = ToolExecutor(max_retries=2, base_delay=0.0)
    ex.register(tool)
    result = ex.execute(1, "flaky", {})
    assert not result.ok and tool.attempts == 1
