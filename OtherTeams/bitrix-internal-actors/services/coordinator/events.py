"""The event the coordinator routes on.

Kept as a plain local dataclass on purpose: it is the seam that will later be
replaced by the team's shared event schema (once `packages/eventbus` /
`packages/schemas` are agreed) without touching the routing rules. For now it
carries just enough to decide "who should wake up."
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActivationEvent:
    kind: str                                # CHAT_MESSAGE | SCENARIO_EVENT
    source: str                              # internal_messaging | scenario
    name: str | None = None                  # scenario name, e.g. SUSPICIOUS_SAMPLE
    channel_id: str | None = None
    message_id: str | None = None
    actor_id: str | None = None              # who caused it (e.g. the sender)
    mentions: list[str] = field(default_factory=list)
    trust_label: str | None = None
    correlation_id: str | None = None
    body: str | None = None
    ts: str | None = None                    # source timestamp / cursor value
