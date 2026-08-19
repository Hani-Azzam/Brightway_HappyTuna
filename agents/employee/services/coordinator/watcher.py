"""The coordinator: watch the world, wake the right agents, log it.

This is the "Event Bus -> Intake" layer the KB describes (§1.2, §10 step 3) and
the COO-Agent branch's pipeline expects. It is infrastructure, not an agent, so
it reads across ALL channels through the Internal Messaging System's firehose
(`MessageReader.all_messages_since`).

Delivery is by polling today (`poll_once`); the ONLY thing that changes when a
real event bus lands is where events come from — the rules, activation, and log
stay identical. `submit()` already lets a scenario engine push events directly.
"""
from __future__ import annotations

from typing import Callable

from services.coordinator.events import ActivationEvent
from services.coordinator.reader import MessageReader
from services.coordinator.rules import route
from services.coordinator import activation_store

# activate(agent_id, event) -> None. Wired to an agent's run-cycle in real use;
# tests inject a fake. Keeping it a plain callable decouples the coordinator from
# any specific agent framework (agentkit vs mcp_core — undecided).
Activate = Callable[[str, ActivationEvent], None]


class Coordinator:
    def __init__(self, activate: Activate, reader: MessageReader) -> None:
        self._activate = activate
        self._reader = reader
        self._cursor: int = 0                # global seq cursor over chat

    def poll_once(self) -> list[tuple[str, ActivationEvent]]:
        """Pick up chat messages posted since the last poll and activate agents.
        Idempotent across calls: the seq cursor advances so no message fires twice."""
        fired: list[tuple[str, ActivationEvent]] = []
        for m in self._reader.all_messages_since(self._cursor):
            event = ActivationEvent(
                kind="CHAT_MESSAGE",
                source="internal_messaging",
                channel_id=m["channel_id"],
                message_id=m["id"],
                actor_id=m["sender_id"],
                mentions=m["mentions"],
                trust_label=m["trust_label"],
                correlation_id=m["correlation_id"],
                body=m["body"],
                ts=m["sim_time"],
            )
            fired.extend(self._dispatch(event))
            self._cursor = m["seq"]
        return fired

    def submit(self, event: ActivationEvent) -> list[tuple[str, ActivationEvent]]:
        """Feed a non-chat event directly (e.g. a scenario engine's
        SUSPICIOUS_SAMPLE). Same routing/activation/logging as chat events."""
        return self._dispatch(event)

    def _dispatch(self, event: ActivationEvent) -> list[tuple[str, ActivationEvent]]:
        fired: list[tuple[str, ActivationEvent]] = []
        for agent_id in route(event):
            activation_store.record(agent_id, event)   # audit/replay artifact
            self._activate(agent_id, event)            # wake the agent
            fired.append((agent_id, event))
        return fired
