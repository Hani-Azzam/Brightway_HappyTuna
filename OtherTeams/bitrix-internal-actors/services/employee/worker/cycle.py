"""One activation = one perceive -> decide -> act cycle.

This is what the coordinator triggers when it decides to wake this employee. The
employee gathers its new observations (from chat), then the persona-driven ReAct
loop decides whether to act (e.g. post a report) and does so through its tools.

If a memory is supplied, the cycle also (a) recalls what the employee already did
into the prompt — so it does not repeat itself — and (b) records ACTIVATED /
OBSERVED / ACTED episodes for audit and replay.
"""
from __future__ import annotations

from packages.agentkit.tool_executor import ToolExecutor

from services.coordinator.events import ActivationEvent
from services.employee.agent.employee_agent import EmployeeAgent
from services.employee.domain.memory import EmployeeMemory
from services.employee.domain.perception import Observation, Perception, PerceptionBundle


def _trigger_from(event: ActivationEvent) -> Observation | None:
    """Turn a non-chat activation into an observation to seed perception.

    Chat messages are already read by perception straight from the channel, so we
    only inject a trigger for events that are NOT in chat (e.g. a scenario
    engine's SUSPICIOUS_SAMPLE) — otherwise the message would be observed twice.
    """
    if event.kind == "CHAT_MESSAGE":
        return None
    return Observation(
        source=event.source,
        trust_label=event.trust_label or "internal",
        ref=event.message_id or event.name or "EVENT",
        body=event.body or event.name or "",
        sender=event.actor_id,
        ts=event.ts,
    )


def _recall_block(memory: EmployeeMemory) -> str:
    done = memory.recent(kind="ACTED", limit=5)
    if not done:
        return ""
    lines = "\n".join(f"  - {e['summary'] or e['ref']}" for e in done)
    return (
        "WHAT YOU HAVE ALREADY DONE (do not repeat these needlessly):\n"
        f"{lines}\n\n"
    )


def _record_actions(memory: EmployeeMemory, executor: ToolExecutor, correlation_id) -> None:
    """One ACTED episode per successful tool call in this cycle (from the trace)."""
    for t in executor.get_traces():
        if t.phase == "ACT" and t.details.startswith("OK"):
            memory.remember("ACTED", ref=t.tool_name, summary=t.details[:120],
                            correlation_id=correlation_id)


def run_cycle(
    agent: EmployeeAgent,
    perception: Perception,
    event: ActivationEvent,
    *,
    memory: EmployeeMemory | None = None,
    executor: ToolExecutor | None = None,
) -> str | None:
    """Perceive, then let the persona decide + act. Returns the agent's final
    answer, or ``None`` if there was nothing new to react to."""
    if memory is not None:
        memory.remember("ACTIVATED", ref=event.message_id or event.name,
                        summary=f"{event.kind} from {event.actor_id}",
                        correlation_id=event.correlation_id)

    bundle: PerceptionBundle = perception.gather(trigger=_trigger_from(event))
    if bundle.is_empty():
        return None

    if memory is not None:
        for o in bundle.observations:
            memory.remember("OBSERVED", ref=o.ref, summary=o.body[:120],
                            correlation_id=event.correlation_id)

    recall = _recall_block(memory) if memory is not None else ""
    task = (
        recall
        + "You have just been activated. Review your new observations below and "
        "decide whether to act (for example, post a report or reply to a "
        "colleague). If action is warranted, use your tools; otherwise briefly "
        "explain why no action is needed.\n\n"
        + bundle.render()
    )
    answer = agent.chat(task)

    if memory is not None and executor is not None:
        _record_actions(memory, executor, event.correlation_id)
    return answer
