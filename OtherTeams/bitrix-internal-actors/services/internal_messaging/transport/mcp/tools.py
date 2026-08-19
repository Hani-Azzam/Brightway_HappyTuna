"""MCP `chat.*` tools — the primary door for `mcp_core` agents (COO, CEO).

Each tool is an `mcp_core.BaseTool`: it declares a `ToolSpec` (name, schema,
`side_effect`, `required_permission`) and implements `_run`, delegating to the
single `InternalMessagingService`. Identity is taken from `ctx.caller_id` — never
from an argument — so an agent cannot impersonate another by crafting args.

`chat.send_message` matches the COO contract exactly
(`{channel, body, to?}` → `ToolResult[MessageReceipt]`).
"""
from __future__ import annotations

from typing import Any

from packages.mcp_core import (
    BaseTool,
    LocalMCPClient,
    SideEffect,
    ToolContext,
    ToolRegistry,
    ToolSpec,
)
from services.internal_messaging.domain.service import InternalMessagingService


class _ChatTool(BaseTool):
    def __init__(self, service: InternalMessagingService) -> None:
        self._service = service


class SendMessageTool(_ChatTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="chat.send_message",
            description="Post a message to an internal-chat channel you belong to.",
            input_schema={
                "type": "object",
                "required": ["channel", "body"],
                "properties": {
                    "channel": {"type": "string"},
                    "body": {"type": "string"},
                    "to": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string"},
                },
            },
            side_effect=SideEffect.WRITE,
            required_permission="chat:write",
        )

    async def _run(self, args: dict[str, Any], ctx: ToolContext) -> Any:
        return self._service.send_message(
            caller_id=ctx.caller_id,
            channel=args.get("channel", ""),
            body=args.get("body", ""),
            to=args.get("to"),
            source=args.get("source", "internal"),
        )


class ReadChannelTool(_ChatTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="chat.read_channel",
            description="Read messages from a channel you belong to; pass `since` for only newer ones.",
            input_schema={
                "type": "object",
                "required": ["channel"],
                "properties": {
                    "channel": {"type": "string"},
                    "since": {"type": "integer"},
                },
            },
            side_effect=SideEffect.READ,
            required_permission="chat:read",
        )

    async def _run(self, args: dict[str, Any], ctx: ToolContext) -> Any:
        return self._service.read_channel(
            caller_id=ctx.caller_id,
            channel=args.get("channel", ""),
            since=int(args.get("since", 0) or 0),
        )


class ListChannelsTool(_ChatTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="chat.list_channels",
            description="List the channels you belong to.",
            input_schema={"type": "object", "properties": {}},
            side_effect=SideEffect.READ,
            required_permission="chat:read",
        )

    async def _run(self, args: dict[str, Any], ctx: ToolContext) -> Any:
        return self._service.list_channels(caller_id=ctx.caller_id)


class CreateChannelTool(_ChatTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="chat.create_channel",
            description="Open a channel (direct/group/incident) and seed its members; you become owner.",
            input_schema={
                "type": "object",
                "required": ["type", "members"],
                "properties": {
                    "type": {"type": "string", "enum": ["direct", "group", "incident"]},
                    "members": {"type": "array", "items": {"type": "string"}},
                    "name": {"type": "string"},
                    "correlation_id": {"type": "string"},
                },
            },
            side_effect=SideEffect.WRITE,
            required_permission="chat:manage",
        )

    async def _run(self, args: dict[str, Any], ctx: ToolContext) -> Any:
        return self._service.create_channel(
            caller_id=ctx.caller_id,
            channel_type=args.get("type", ""),
            members=list(args.get("members", []) or []),
            name=args.get("name"),
            correlation_id=args.get("correlation_id"),
        )


class AddMemberTool(_ChatTool):
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="chat.add_member",
            description="Add a member to a channel you own.",
            input_schema={
                "type": "object",
                "required": ["channel", "agent_id"],
                "properties": {
                    "channel": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "role": {"type": "string"},
                },
            },
            side_effect=SideEffect.WRITE,
            required_permission="chat:manage",
        )

    async def _run(self, args: dict[str, Any], ctx: ToolContext) -> Any:
        return self._service.add_member(
            caller_id=ctx.caller_id,
            channel=args.get("channel", ""),
            agent_id=args.get("agent_id", ""),
            role=args.get("role", "member"),
        )


def build_chat_tools(service: InternalMessagingService) -> list[BaseTool]:
    return [
        SendMessageTool(service),
        ReadChannelTool(service),
        ListChannelsTool(service),
        CreateChannelTool(service),
        AddMemberTool(service),
    ]


def build_chat_client(service: InternalMessagingService) -> LocalMCPClient:
    """A ready in-process MCP client exposing the `chat.*` tools. A remote
    transport later reuses the same `MCPClient` contract — callers don't change."""
    registry = ToolRegistry(list(build_chat_tools(service)))
    return LocalMCPClient(registry)
