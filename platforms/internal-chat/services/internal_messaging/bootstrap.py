"""Seed the initial channels the world needs so agents can actually talk.

A fresh Internal Messaging System has an empty store: every `send`/`read` would
fail (NOT_FOUND / not-a-member) until some channels and memberships exist. This
script creates the starting rooms for the HappyTuna scenario — today, the incident
room the COO owns and the QA employee + CEO belong to.

Idempotent: it skips a channel whose `correlation_id` the COO already owns, so
re-running (or a container restart against a persisted DB) does not duplicate rooms.

Run against the configured DB:
    python -m services.internal_messaging.bootstrap
"""
from __future__ import annotations

from packages.schemas.tool_results import ChannelReceipt
from services.internal_messaging.domain.service import InternalMessagingService

# One row per starting channel: (owner, type, members, name, correlation_id).
_WORLD_CHANNELS = [
    ("COO-1", "incident", ["EMP-QA-17", "CEO-1"], "ht-crisis", "HT-2026-001"),
]


def seed_world(service: InternalMessagingService, *, force: bool = False) -> list[ChannelReceipt]:
    """Create any missing world channels. Returns the receipts actually created."""
    existing = {c.correlation_id for c in service.list_channels("COO-1").channels}
    created: list[ChannelReceipt] = []
    for owner, ctype, members, name, correlation_id in _WORLD_CHANNELS:
        if correlation_id in existing and not force:
            continue
        created.append(
            service.create_channel(
                caller_id=owner,
                channel_type=ctype,
                members=members,
                name=name,
                correlation_id=correlation_id,
            )
        )
    return created


def main() -> None:
    from services.internal_messaging.app.main import build_service

    service = build_service()
    created = seed_world(service)
    if not created:
        print("world already seeded — nothing to do.")
        return
    for r in created:
        print(f"created {r.type} channel {r.channel}")


if __name__ == "__main__":
    main()
