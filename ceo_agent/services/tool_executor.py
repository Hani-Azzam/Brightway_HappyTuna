import time
from dataclasses import dataclass
#from msilib import schema

from base.tool_base import ToolBase, ToolBase, ToolResult


@dataclass
class StepTrace:
    step: int
    phase: str
    tool_name: str | None
    details: str
    duration_ms: float = 0.0


class ToolExecutor:
    def __init__(self, max_retries: int = 2, base_delay: float = 0.5) -> None:
        """
        max_retries - hw many extra attempts after the first failure
        base_delay - base wait in seconds; doubled on each retry attempt
        """
        self._registry: dict[str, ToolBase] = {}
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._trace: list[StepTrace] = []

    def register(self, tool: ToolBase) -> None:
        """
        Concept: Tool Registry - Agent development (15% of certificate test)
        Maps tool schema to tool instances
        """
        # MISSING ^
        self._registry[tool.schema.name] = tool


    def tool_schemas(self) -> list[dict]:
        """Returns all registered tool schemas as plain english for prompt injection."""
        return  [
            {
                "name": t.schema.name,
                "description": t.schema.description,
                "parameters": t.schema.parameters,
            }
            for t in self._registry.values()
        ]


    def execute(self, step: int, tool_name: str, args: dict) -> ToolResult:
        """
        idk
        Runs the named tool after two validation checks:
            1. Tool existance - rejects invented tools
            2. Required args
        """
        # Failure matrix: invented tool name
        if tool_name not in self._registry:
            result = ToolResult(
                error=f"Unknown tool {tool_name}."
                f"Available tools: {list(self._registry.keys())}"
            )
            self._trace.append(StepTrace(
                step, "ACT", tool_name,
                f"FAIL - unknown tool  args={args}",
            ))
            return result

        tool = self._registry[tool_name]

        # Failure matrix: missing required arguments (schema enforcement)
        required = tool.schema.parameters.get("required", [])
        missing = [p for p in required if p not in args]
        if missing:
            result = ToolResult(error=f"missing required arguments: {missing}")
            self._trace.append(StepTrace(
                step, "ACT", tool_name,
                f"FAIL - missing args {missing}  provided={list(args.keys())}",
            ))
            return result

        # Run with retry + exponential backoff
        max_attempts = self.max_retries + 1
        last_result: ToolResult | None = None

        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                delay = self.base_delay * (2 ** (attempt - 2))
                time.sleep(delay)

            t0 = time.monotonic()
            try:
                last_result = tool.run(**args)
            except Exception as exc:
                last_result = ToolResult(error=f"Unexpected exception: {exc}")
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

            attempt_label = f"attempt {attempt}/{max_attempts}"

            if last_result.ok:
                self._trace.append(StepTrace(
                    step, "ACT", tool_name,
                    f"OK  {attempt_label}  args={args}  -> {str(last_result.value)[:80]}",
                    elapsed_ms,
                ))
                return last_result

            # Log the failed attemp
            self._trace.append(StepTrace(
                step, "ACT", tool_name,
                f"FAIL {attempt_label}  error: {last_result.error}",
                elapsed_ms,
            ))

            # Non-idempotent: do NOT retry (side effects already happened)
            if not last_result.is_idempotent:
                break

        return last_result


    def log_trace(self, step: int, phase: str, tool_name: str | None, details: str) -> None:
        """Records a PLAN or OBSERVE trace entry (no tool execution time)."""
        self._trace.append(StepTrace(step, phase, tool_name, details))


    def get_traces(self) -> list[StepTrace]:
        return list(self._trace)


    def clear_traces(self) -> None:
        self._trace.clear()







