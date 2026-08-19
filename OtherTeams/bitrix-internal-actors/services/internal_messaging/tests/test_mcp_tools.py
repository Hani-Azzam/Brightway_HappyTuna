"""P2 — the MCP door: `chat.*` tools return `ToolResult`, deny → failure."""
from __future__ import annotations

from packages.schemas.tool_results import ChannelHistory, ChannelReceipt, MessageReceipt
from services.internal_messaging.transport.mcp.tools import build_chat_client


async def test_create_send_read_roundtrip(service, ctx):
    client = build_chat_client(service)

    created = await client.call_tool(
        "chat.create_channel",
        {"type": "incident", "members": ["EMP-QA-17"], "correlation_id": "HT-2026-001"},
        ctx("COO-1", "coo"),
    )
    assert created.ok
    assert isinstance(created.value, ChannelReceipt)
    channel = created.value.channel

    sent = await client.call_tool(
        "chat.send_message",
        {"channel": channel, "body": "Line 4 halted @COO-1"},
        ctx("EMP-QA-17"),
    )
    assert sent.ok
    assert isinstance(sent.value, MessageReceipt)
    assert set(sent.value.delivered_to) == {"COO-1", "EMP-QA-17"}
    # ResultMeta is attached for audit/replay
    assert sent.meta is not None and sent.meta.tool == "chat.send_message"

    read = await client.call_tool("chat.read_channel", {"channel": channel}, ctx("COO-1", "coo"))
    assert read.ok
    assert isinstance(read.value, ChannelHistory)
    assert read.value.messages[0].body == "Line 4 halted @COO-1"


async def test_non_member_send_returns_failure_not_exception(service, ctx):
    client = build_chat_client(service)
    created = await client.call_tool(
        "chat.create_channel", {"type": "group", "members": ["EMP-QA-17"]}, ctx("COO-1", "coo")
    )
    channel = created.value.channel

    res = await client.call_tool(
        "chat.send_message", {"channel": channel, "body": "hi"}, ctx("OUTSIDER-1")
    )
    assert res.failed
    assert res.error is not None
    assert res.error.code.value == "UNAUTHORIZED"


async def test_missing_body_is_validation_failure(service, ctx):
    client = build_chat_client(service)
    created = await client.call_tool(
        "chat.create_channel", {"type": "group", "members": ["EMP-QA-17"]}, ctx("COO-1", "coo")
    )
    res = await client.call_tool(
        "chat.send_message", {"channel": created.value.channel}, ctx("EMP-QA-17")
    )
    assert res.failed
    assert res.error.code.value == "VALIDATION"
