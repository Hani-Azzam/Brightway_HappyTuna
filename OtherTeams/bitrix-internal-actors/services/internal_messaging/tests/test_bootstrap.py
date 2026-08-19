"""The world bootstrap: creates the starting rooms, idempotently, with the right
members — so agents can send/read immediately and non-members still can't."""
from __future__ import annotations

import pytest

from packages.mcp_core.errors import ToolAuthorizationError
from services.internal_messaging.bootstrap import seed_world


def test_seed_creates_incident_room_members_can_use(service):
    created = seed_world(service)
    assert len(created) == 1
    channel = created[0].channel
    assert created[0].type == "incident"

    # Members can post and read straight away.
    service.send_message("EMP-QA-17", channel, "Line 4 flagged @COO-1")
    assert service.read_channel("COO-1", channel).messages[0].sender == "EMP-QA-17"
    assert service.read_channel("CEO-1", channel).messages[0].body == "Line 4 flagged @COO-1"


def test_seed_is_idempotent(service):
    assert len(seed_world(service)) == 1
    assert seed_world(service) == []                 # second run creates nothing
    # COO owns exactly one HT-2026-001 room, not two.
    rooms = [c for c in service.list_channels("COO-1").channels
             if c.correlation_id == "HT-2026-001"]
    assert len(rooms) == 1


def test_non_member_is_isolated_from_seeded_room(service):
    channel = seed_world(service)[0].channel
    # OUTSIDER-1 (unlisted -> employee role, has chat:read) is still not a member.
    with pytest.raises(ToolAuthorizationError):
        service.read_channel("OUTSIDER-1", channel)
