"""The cross-channel firehose (`all_messages_since`) that the activation layer polls.

Two guarantees: (1) a `chat:system` reader sees every post across all channels in
seq order; (2) NO agent role — not even the CEO — can call it, so reading across
channels stays impossible for agents (R8 isolation).
"""
from __future__ import annotations

import pytest

from packages.mcp_core.errors import ToolAuthorizationError
from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.integration.identity import Registry


@pytest.fixture
def coord_registry() -> Registry:
    return Registry(
        {
            "COO-1": "coo",
            "CEO-1": "ceo",
            "EMP-QA-17": "employee",
            "COORD-1": "coordinator",   # -> chat:system
        }
    )


@pytest.fixture
def coord_service(store, coord_registry, publisher) -> InternalMessagingService:
    return InternalMessagingService(store, coord_registry, publisher)


def test_firehose_spans_channels_in_seq_order(coord_service):
    a = coord_service.create_channel("COO-1", "group", ["EMP-QA-17"], name="a").channel
    b = coord_service.create_channel("COO-1", "incident", ["EMP-QA-17"],
                                     correlation_id="HT-1").channel
    coord_service.send_message("EMP-QA-17", a, "first @COO-1")
    coord_service.send_message("COO-1", b, "second")
    coord_service.send_message("EMP-QA-17", a, "third")

    rows = coord_service.all_messages_since("COORD-1", since=0)
    assert [r["body"] for r in rows] == ["first @COO-1", "second", "third"]
    assert [r["channel_id"] for r in rows] == [a, b, a]
    assert rows[0]["mentions"] == ["COO-1"]              # decoded, ready to route
    assert rows[1]["correlation_id"] == "HT-1"

    # cursor advances: only newer posts on the next poll
    cursor = rows[1]["seq"]
    assert [r["body"] for r in coord_service.all_messages_since("COORD-1", cursor)] == ["third"]


def test_agents_cannot_read_the_firehose(coord_service):
    coord_service.create_channel("COO-1", "group", ["EMP-QA-17"], name="a")
    for agent in ("COO-1", "CEO-1", "EMP-QA-17"):
        with pytest.raises(ToolAuthorizationError):
            coord_service.all_messages_since(agent, since=0)
