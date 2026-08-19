"""Routing rules: event -> which agents to activate.

Deterministic on purpose (KB §1.2: use deterministic rules for safety-critical
triggers, LLM routing only for ambiguous social cues). No LLM here. This is the
whole "who cares about this?" decision, kept in one small, testable place.
"""
from __future__ import annotations

from services.coordinator.events import ActivationEvent

# Safety-critical scenario events map to a fixed set of agents.
SCENARIO_ACTIVATIONS: dict[str, list[str]] = {
    "SUSPICIOUS_SAMPLE": ["EMP-QA-17", "COO-1"],
    "LAB_RESULT": ["EMP-QA-17", "COO-1"],
}


def route(event: ActivationEvent) -> list[str]:
    """Return the agent ids to activate for this event (order preserved, deduped)."""
    if event.kind == "CHAT_MESSAGE":
        # Wake anyone mentioned, but never the sender (no self-activation).
        woken: list[str] = []
        for agent_id in event.mentions:
            if agent_id != event.actor_id and agent_id not in woken:
                woken.append(agent_id)
        return woken

    if event.kind == "SCENARIO_EVENT" and event.name:
        return list(SCENARIO_ACTIVATIONS.get(event.name.upper(), []))

    return []
