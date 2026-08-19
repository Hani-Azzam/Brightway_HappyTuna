"""Glue between the coordinator and the employee agents.

The coordinator decides *who* to wake (see `services/coordinator`); this module
says *what waking an employee does* — run its cycle. The dependency points one
way only: employee -> coordinator. The coordinator never imports the employee;
it just calls the `activate` callback this module builds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from packages.agentkit.tool_executor import ToolExecutor

from services.coordinator.events import ActivationEvent
from services.employee.agent.employee_agent import EmployeeAgent
from services.employee.domain.memory import EmployeeMemory
from services.employee.domain.perception import Perception
from services.employee.worker.cycle import run_cycle


@dataclass
class EmployeeRuntime:
    """Everything needed to run one employee's cycle.

    `memory` and `executor` are optional: without them the cycle still runs (no
    recall, no recording) — that keeps lightweight/test wiring simple. With them,
    the employee remembers what it did and its actions are recorded for replay.
    """

    agent: EmployeeAgent
    perception: Perception
    memory: EmployeeMemory | None = None
    executor: ToolExecutor | None = None

    def activate(self, event: ActivationEvent) -> str | None:
        # One bad cycle (LLM error, tool failure, …) must never crash the worker —
        # log it and move on, so other activations/personas keep running (KB §4.5,
        # tech-design §12). The coordinator's cursor still advances, so the failing
        # message is not retried in a tight loop.
        eid = self.agent.employee_id
        print(f"[employee] {eid} activated by {event.kind} "
              f"({event.message_id or event.name or '-'})")
        try:
            answer = run_cycle(
                self.agent, self.perception, event,
                memory=self.memory, executor=self.executor,
            )
        except Exception as exc:  # noqa: BLE001 — deliberately broad: resilience boundary
            print(f"[employee] {eid} cycle failed ({type(exc).__name__}: {exc}); continuing.")
            if self.memory is not None:
                self.memory.remember("ERROR", ref=event.message_id or event.name,
                                     summary=f"{type(exc).__name__}: {exc}"[:120],
                                     correlation_id=event.correlation_id)
            return None
        if answer is None:
            print(f"[employee] {eid} had nothing new to act on.")
        else:
            print(f"[employee] {eid} acted → {answer[:160]}")
        return answer


def make_activator(
    runtimes: dict[str, EmployeeRuntime],
) -> Callable[[str, ActivationEvent], None]:
    """Build the coordinator's `activate` callback from a set of employees.

    Activations for agent ids we don't run here (e.g. the COO) are ignored, so
    the same coordinator can drive several role services independently.
    """

    def activate(agent_id: str, event: ActivationEvent) -> None:
        runtime = runtimes.get(agent_id)
        if runtime is not None:
            runtime.activate(event)

    return activate
