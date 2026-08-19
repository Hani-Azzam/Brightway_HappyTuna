"""Validates, runs, and retries tool calls; records a full step trace.

The trace is not just for debugging: for the Employee (and other simulated
actors) it is the raw material of the decision record that Team 4 evaluation
replays. Keep it faithful.

Tool failure matrix:
    Invented tool name   → immediate error, no run()
    Missing required arg → immediate error, no run()
    Business-rule fail   → tool returns ToolResult(error=...) from run()
    Unexpected exception → caught, wrapped in ToolResult(error=...)

Retry policy:
    is_idempotent=True  → retry up to max_retries with exponential backoff
    is_idempotent=False → execute exactly once (writes must not be blind-retried)
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from packages.agentkit.tool_base import ToolBase, ToolResult


@dataclass
class StepTrace:
    step: int
    phase: str              # PLAN | ACT | OBSERVE
    tool_name: str | None
    details: str
    duration: float = 0.0   # milliseconds


class ToolExecutor:
    def __init__(self, max_retries: int = 2, base_delay: float = 0.5) -> None:
        self._registry: dict[str, ToolBase] = {}
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._traces: list[StepTrace] = []

    def register(self, tool: ToolBase) -> None:
        self._registry[tool.schema.name] = tool

    def tool_schemas(self) -> list[dict]:
        return [
            {
                "name": t.schema.name,
                "description": t.schema.description,
                "parameters": t.schema.parameters,
            }
            for t in self._registry.values()
        ]

    def execute(self, step: int, tool_name: str, args: dict) -> ToolResult:
        if tool_name not in self._registry:
            self._traces.append(
                StepTrace(step, "ACT", tool_name, f"FAIL — unknown tool, args={args}")
            )
            return ToolResult(
                error=f"Unknown tool '{tool_name}'. Available: {list(self._registry)}"
            )

        tool = self._registry[tool_name]
        required = tool.schema.parameters.get("required", [])
        missing = [p for p in required if p not in args]
        if missing:
            self._traces.append(
                StepTrace(step, "ACT", tool_name, f"FAIL — missing args {missing}")
            )
            return ToolResult(error=f"Missing required arguments: {missing}")

        max_attempts = self._max_retries + 1
        last: ToolResult | None = None
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                time.sleep(self._base_delay * (2 ** (attempt - 2)))
            t0 = time.monotonic()
            try:
                last = tool.run(**args)
            except Exception as exc:  # noqa: BLE001 — tool code is untrusted; never crash the loop
                last = ToolResult(error=f"Unhandled exception: {exc}")
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            label = f"attempt {attempt}/{max_attempts}"
            if last.ok:
                self._traces.append(
                    StepTrace(
                        step, "ACT", tool_name,
                        f"OK {label} args={args} → {str(last.value)[:80]}", elapsed,
                    )
                )
                return last
            self._traces.append(
                StepTrace(step, "ACT", tool_name, f"FAIL {label} error: {last.error}", elapsed)
            )
            if not last.is_idempotent:
                break
        return last  # type: ignore[return-value]

    def log_trace(self, step: int, phase: str, tool_name: str | None, details: str) -> None:
        self._traces.append(StepTrace(step, phase, tool_name, details))

    def get_traces(self) -> list[StepTrace]:
        return list(self._traces)

    def clear_traces(self) -> None:
        self._traces.clear()
