"""Shared test doubles for agentkit."""
from __future__ import annotations

from packages.agentkit.tool_base import ToolBase, ToolResult, ToolSchema


class FakeLlm:
    """Returns pre-scripted responses in order; records what it was asked.

    Satisfies the `LLM` protocol (single `invoke` method) with no network.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def invoke(self, messages: list[dict]) -> str:
        self.calls.append([dict(m) for m in messages])  # snapshot; agent mutates the live list
        if not self._responses:
            raise AssertionError("FakeLlm ran out of scripted responses")
        return self._responses.pop(0)


class AddTool(ToolBase):
    """Adds two numbers. Idempotent."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="add",
            description="Add two integers a and b.",
            parameters={
                "type": "object",
                "required": ["a", "b"],
                "properties": {
                    "a": {"type": "integer", "description": "first addend"},
                    "b": {"type": "integer", "description": "second addend"},
                },
            },
        )

    def run(self, a: int, b: int) -> ToolResult:
        return ToolResult(value=int(a) + int(b))


class BoomTool(ToolBase):
    """Always fails — used to exercise the error path."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="boom",
            description="Always raises.",
            parameters={"type": "object", "required": [], "properties": {}},
        )

    def run(self) -> ToolResult:
        raise RuntimeError("kaboom")
