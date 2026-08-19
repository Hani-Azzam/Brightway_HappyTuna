"""The remote MCP door: an `mcp_core` agent (COO) reaches chat OVER HTTP.

The `HttpMCPClient` speaks the same `MCPClient` contract as `LocalMCPClient`, so
this is exactly how the COO — running as its own service — calls chat. The
transport here is a `TestClient`, standing in for the network.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from packages.mcp_core.http_client import HttpMCPClient
from services.internal_messaging.transport.rest.app import create_rest_app


@pytest.fixture
def transport(service):
    return TestClient(create_rest_app(service))


async def test_coo_and_employee_each_as_own_service_over_the_wire(transport):
    coo = HttpMCPClient(http=transport, agent_id="COO-1")
    emp = HttpMCPClient(http=transport, agent_id="EMP-QA-17")

    specs = await coo.list_tools()
    assert "chat.send_message" in {s.name for s in specs}

    created = await coo.call_tool(
        "chat.create_channel",
        {"type": "incident", "members": ["EMP-QA-17"], "correlation_id": "HT-2026-001"},
    )
    assert created.ok
    channel = created.value["channel"]           # value arrives as a dict over the wire

    sent = await emp.call_tool(
        "chat.send_message", {"channel": channel, "body": "Line 4 halted @COO-1"}
    )
    assert sent.ok
    assert set(sent.value["delivered_to"]) == {"COO-1", "EMP-QA-17"}
    assert sent.meta.tool == "chat.send_message"  # ResultMeta survives the round trip

    read = await coo.call_tool("chat.read_channel", {"channel": channel})
    assert read.ok
    assert read.value["messages"][0]["body"] == "Line 4 halted @COO-1"


async def test_non_member_denied_over_the_wire(transport):
    coo = HttpMCPClient(http=transport, agent_id="COO-1")
    created = await coo.call_tool("chat.create_channel", {"type": "group", "members": ["EMP-QA-17"]})
    channel = created.value["channel"]

    outsider = HttpMCPClient(http=transport, agent_id="OUTSIDER-1")
    res = await outsider.call_tool("chat.send_message", {"channel": channel, "body": "hi"})
    assert res.failed
    assert res.error.code.value == "UNAUTHORIZED"


async def test_identity_is_the_bearer_not_the_body(transport):
    coo = HttpMCPClient(http=transport, agent_id="COO-1")
    channel = (
        await coo.call_tool("chat.create_channel", {"type": "incident", "members": ["EMP-QA-17"]})
    ).value["channel"]

    emp = HttpMCPClient(http=transport, agent_id="EMP-QA-17")
    await emp.call_tool("chat.send_message", {"channel": channel, "body": "mine"})

    read = await coo.call_tool("chat.read_channel", {"channel": channel})
    assert read.value["messages"][-1]["sender"] == "EMP-QA-17"
