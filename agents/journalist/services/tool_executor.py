import time
from dataclasses import dataclass

from base.tool_base import ToolBase, ToolResult


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
        max_retries  - how many extra attempts after the first failure
        base_delay   - base wait in seconds; doubled on each retry attempt
        """
        self._registry: dict[str, ToolBase] = {}
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._traces: list[StepTrace] = []


    def register(self, tool: ToolBase) -> None:
        """
        Concept: Tool Registry - Agent Development (15%)

        Maps tool schema names to tool instances.
        ToolAgent looks up tools by name from the LLM's JSON output -
        if the LLM invents a name that is not in the registry, execute()
        returns an error immediately instead of crashing.
        """
        self._registry[tool.schema.name] = tool


    def tool_schemas(self) -> list[dict]:
        """Returns all registered tool schemas as plain dicts for prompt injection."""
        return [
            {
                "name": t.schema.name,
                "description": t.schema.description,
                "parameters": t.schema.parameters,
            }
            for t in self._registry.values()
        ]

    def execute(self, step: int, tool_name: str, args: dict) -> ToolResult:
        """
        Runs the named tool after two validation checks:
            1. Tool existence  - rejects invented tool names immediately
            2. Required args   - rejects calls missing mandatory parameters

        Then runs with exponential backoff retry for idempotent tools.
        """
        # Failure matrix: invented tool name
        if tool_name not in self._registry:
            result = ToolResult(
                error=f"Unknown tool '{tool_name}'. "
                      f"Available tools: {list(self._registry.keys())}"
            )
            self._traces.append(StepTrace(
                step, "ACT", tool_name,
                f"FAIL - unknown tool  args={args}",
            ))
            return result

        tool = self._registry[tool_name]

        # Failure matrix: missing required arguments (schema enforcement)
        required = tool.schema.parameters.get("required", [])
        missing = [p for p in required if p not in args]
        if missing:
            result = ToolResult(error=f"Missing required arguments: {missing}")
            self._traces.append(StepTrace(
                step, "ACT", tool_name,
                f"FAIL - missing args {missing}  provided={list(args.keys())}",
            ))
            return result

        # Run with retry + exponential backoff
        max_attempts = self._max_retries + 1
        last_result: ToolResult | None = None

        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                delay = self._base_delay * (2 ** (attempt - 2))
                time.sleep(delay)

            t0 = time.monotonic()
            try:
                last_result = tool.run(**args)
            except Exception as exc:
                last_result = ToolResult(error=f"Unexpected exception: {exc}")
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1) # 2.54 --> 2.6

            attempt_label = f"attempt {attempt}/{max_attempts}"

            if last_result.ok:
                self._traces.append(StepTrace(
                    step, "ACT", tool_name,
                    f"OK  {attempt_label}  args={args} -> {str(last_result.value)[:80]}",
                    elapsed_ms,
                ))
                return last_result

                # Log the failed attempt
            self._traces.append(StepTrace(
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
        self._traces.append(StepTrace(step, phase, tool_name, details))

    def get_traces(self) -> list[StepTrace]:
        return list(self._traces)

    def clear_traces(self) -> None:
        self._traces.clear()