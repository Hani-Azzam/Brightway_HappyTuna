"""Standard MCP server for the Internal Chat platform (streamable-http).

The chat's original "MCP door" is a bespoke REST envelope (`/mcp/chat/call`,
identity = Bearer header). Agents built on the real MCP protocol — the CEO
gateway in particular — speak streamable-http and bind identity per MCP
session via a `login` tool, exactly like the social network's MCP server does.
This module provides that door.

Identity model: `login(agent_id)` stores the caller id against THIS MCP
session; every later tool call runs as that agent (the id is never a tool
argument, so a model cannot impersonate someone else mid-session). A write
tool called before `login` fails cleanly with a 401-style message.

All real work is delegated to the same in-process tool registry the REST door
uses (`build_chat_client`), so validation, role permissions, and membership
checks live in exactly one place (`domain/service.py`).

Run standalone (shares the SQLite volume with the REST container):
    MCP_PORT=8090 python -m services.internal_messaging.mcp_server
"""
from __future__ import annotations

import os
import weakref
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP

from packages.mcp_core import ToolContext
from services.internal_messaging.app.config import load_settings
from services.internal_messaging.app.main import build_service
from services.internal_messaging.transport.mcp.tools import build_chat_client

_settings = load_settings()
_service = build_service(_settings)
_client = build_chat_client(_service)
_registry = _service.registry

# MCP session -> logged-in agent id. Weak keys: entries die with their session.
_identities: "weakref.WeakKeyDictionary[Any, str]" = weakref.WeakKeyDictionary()

mcp = FastMCP(
    name="internal-chat",
    host="0.0.0.0",
    port=int(os.environ.get("MCP_PORT", 8090)),
)


def _caller(ctx: Context) -> str:
    agent_id = _identities.get(ctx.session)
    if not agent_id:
        raise ValueError('401: not logged in. Call the "login" tool first.')
    return agent_id


async def _call(ctx: Context, tool: str, args: dict) -> dict:
    """Run one registry tool as the session's agent, unwrapping the envelope."""
    agent_id = _caller(ctx)
    tool_ctx = ToolContext(caller_id=agent_id, caller_role=_registry.role_of(agent_id))
    result = await _client.call_tool(tool, args, tool_ctx)
    payload = result.model_dump(mode="json")
    if not payload["ok"]:
        error = payload.get("error") or {}
        raise ValueError(error.get("message") or "tool failed")
    return payload["value"]


@mcp.tool()
async def login(agent_id: str, ctx: Context) -> dict:
    """Bind this session to an agent identity (e.g. "CEO-1" or "EMP-QA-17").

    All later tool calls act as this agent. The server resolves the agent's
    role from its own registry — the id selects who you are, not what you may
    do. Returns the agent id and its resolved role.
    """
    agent_id = (agent_id or "").strip()
    if not agent_id:
        raise ValueError("agent_id must be a non-empty string")
    _identities[ctx.session] = agent_id
    return {"agent_id": agent_id, "role": _registry.role_of(agent_id)}


@mcp.tool()
async def list_channels(ctx: Context) -> dict:
    """List the chat channels you belong to (id, type, name)."""
    return await _call(ctx, "chat.list_channels", {})


@mcp.tool()
async def read_channel(channel: str, since: int = 0, ctx: Context = None) -> dict:
    """Read messages from a channel you belong to, oldest first.

    Args:
        channel: The channel id (from list_channels).
        since: Only return messages newer than this cursor; pass the
            next_cursor from a previous read to page forward.
    """
    return await _call(ctx, "chat.read_channel", {"channel": channel, "since": since})


@mcp.tool()
async def send_message(channel: str, body: str, ctx: Context = None) -> dict:
    """Post a message to an internal-chat channel you belong to.

    Use @agent-id mentions (e.g. "@EMP-QA-17") to address someone directly —
    mentioned employees are woken up to read and respond.
    """
    return await _call(ctx, "chat.send_message", {"channel": channel, "body": body})


@mcp.tool()
async def create_channel(
    type: str,
    members: list[str],
    name: Optional[str] = None,
    correlation_id: Optional[str] = None,
    ctx: Context = None,
) -> dict:
    """Open a channel and seed its members; you become the owner.

    Args:
        type: One of "direct" (exactly 2 members), "group", or "incident".
        members: Agent ids to include (you are added automatically).
        name: Optional human-readable channel name.
        correlation_id: Optional incident/correlation tag.
    """
    return await _call(ctx, "chat.create_channel", {
        "type": type, "members": members, "name": name, "correlation_id": correlation_id,
    })


@mcp.tool()
async def add_member(channel: str, agent_id: str, ctx: Context = None) -> dict:
    """Add a member to a channel you own."""
    return await _call(ctx, "chat.add_member", {"channel": channel, "agent_id": agent_id})


def _seed_incident_channel() -> None:
    """Idempotently create the standing crisis room (CEO + every employee).

    Gives the CEO and the employee population a shared channel from the first
    boot, so leadership can convene without first discovering everyone's id.
    Guarded by CHAT_SEED=false for a completely empty world.
    """
    if os.environ.get("CHAT_SEED", "true").lower() not in ("1", "true", "yes"):
        return
    correlation = "HT-2026-001"
    existing = _service.list_channels(caller_id="CEO-1")
    for summary in existing.channels:
        if getattr(summary, "correlation_id", None) == correlation:
            print(f"[internal-chat-mcp] world already seeded (channel {summary.channel})")
            return
    receipt = _service.create_channel(
        caller_id="CEO-1",
        channel_type="incident",
        members=["EMP-QA-17", "PROD-WORKER-3", "PLANT-MGR-1",
                 "CONCERNED-EMP-1", "WHISTLEBLOWER-1"],
        name="ht-crisis",
        correlation_id=correlation,
    )
    print(f"[internal-chat-mcp] seeded incident channel {receipt.channel}")


if __name__ == "__main__":
    _seed_incident_channel()
    mcp.run(transport="streamable-http")
