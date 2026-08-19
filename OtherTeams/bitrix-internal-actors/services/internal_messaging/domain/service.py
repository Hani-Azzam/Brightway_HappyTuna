"""The one place business rules + authorization live.

Both transports (MCP tools, REST routes) call this service, so membership and
authority are enforced identically regardless of how the caller arrived (KB §4.1).
It raises `mcp_core` errors so the MCP layer returns a uniform `ToolResult` and
the REST layer maps codes to HTTP — one taxonomy, two doors.

Identity is always the authenticated caller (`caller_id`), never a payload field
— this is what makes CEO isolation and anti-impersonation structural, not prompt.
"""
from __future__ import annotations

import re
from datetime import datetime

from packages.mcp_core.errors import ToolAuthorizationError, ToolNotFoundError, ToolValidationError
from packages.schemas.tool_results import (
    ChannelHistory,
    ChannelList,
    ChannelReceipt,
    ChannelSummary,
    ChatMessage,
    MembershipAck,
    MessageReceipt,
)
from services.internal_messaging.domain.models import ChannelType, trust_label_for
from services.internal_messaging.domain.store_base import StoreProtocol
from services.internal_messaging.integration.cache import Cache, NullCache
from services.internal_messaging.integration.events import ChatMessagePosted, NullPublisher, Publisher
from services.internal_messaging.integration.identity import Registry

_MENTION_RE = re.compile(r"@([\w-]+)")
_VALID_SOURCES = {"internal", "external", "anonymous"}


class InternalMessagingService:
    def __init__(
        self,
        store: StoreProtocol,
        registry: Registry,
        publisher: Publisher | None = None,
        cache: Cache | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._publisher = publisher or NullPublisher()
        self._cache = cache or NullCache()

    def _members(self, channel: str) -> list[str]:
        """Channel roster, read-through the active-state cache (store is truth)."""
        cached = self._cache.get_members(channel)
        if cached is not None:
            return cached
        members = self._store.members(channel)
        self._cache.set_members(channel, members)
        return members

    @property
    def registry(self) -> Registry:
        """Identity/permission source — used by the HTTP MCP transport to resolve
        the authenticated caller's role."""
        return self._registry

    # --- authority helpers ------------------------------------------------

    def _require_permission(self, caller_id: str, permission: str) -> None:
        if not self._registry.can(caller_id, permission):
            raise ToolAuthorizationError(
                f"'{caller_id}' lacks permission '{permission}'",
                details={"caller": caller_id, "permission": permission},
            )

    def _require_channel(self, channel: str) -> dict:
        ch = self._store.get_channel(channel)
        if ch is None:
            raise ToolNotFoundError(f"No channel '{channel}'", details={"channel": channel})
        return ch

    def _require_member(self, channel: str, caller_id: str) -> None:
        if not self._store.is_member(channel, caller_id):
            # Same response whether the channel is missing or the caller simply
            # isn't in it — never confirm existence to a non-member (isolation).
            raise ToolAuthorizationError(
                f"'{caller_id}' is not a member of channel '{channel}'",
                details={"caller": caller_id, "channel": channel},
            )

    # --- channels ---------------------------------------------------------

    def create_channel(
        self,
        caller_id: str,
        channel_type: str,
        members: list[str],
        name: str | None = None,
        correlation_id: str | None = None,
    ) -> ChannelReceipt:
        self._require_permission(caller_id, "chat:manage")
        try:
            ctype = ChannelType(channel_type)
        except ValueError:
            raise ToolValidationError(
                f"Unknown channel type '{channel_type}'",
                details={"allowed": [t.value for t in ChannelType]},
            ) from None

        roster = {caller_id, *members}
        if ctype is ChannelType.DIRECT and len(roster) != 2:
            raise ToolValidationError(
                "direct channels require exactly 2 members",
                details={"members": sorted(roster)},
            )

        ch = self._store.create_channel(
            channel_type=ctype.value,
            name=name,
            correlation_id=correlation_id,
            creator=caller_id,
            members=list(members),
        )
        return ChannelReceipt(
            channel=ch["id"],
            type=ch["type"],
            created_at=datetime.fromisoformat(ch["sim_time"]),
        )

    def add_member(
        self,
        caller_id: str,
        channel: str,
        agent_id: str,
        role: str = "member",
    ) -> MembershipAck:
        self._require_permission(caller_id, "chat:manage")
        self._require_channel(channel)
        if self._store.member_role(channel, caller_id) != "owner":
            raise ToolAuthorizationError(
                f"only the channel owner may add members to '{channel}'",
                details={"caller": caller_id, "channel": channel},
            )
        self._store.add_member(channel, agent_id, role)
        self._cache.invalidate_members(channel)   # roster changed
        return MembershipAck(channel=channel, agent_id=agent_id, role=role)

    def list_channels(self, caller_id: str) -> ChannelList:
        self._require_permission(caller_id, "chat:read")
        rows = self._store.channels_for(caller_id)
        return ChannelList(
            channels=[
                ChannelSummary(
                    channel=r["id"],
                    type=r["type"],
                    name=r["name"],
                    correlation_id=r["correlation_id"],
                    member_count=r["member_count"],
                )
                for r in rows
            ]
        )

    # --- messages ---------------------------------------------------------

    def send_message(
        self,
        caller_id: str,
        channel: str,
        body: str,
        to: list[str] | None = None,
        source: str = "internal",
    ) -> MessageReceipt:
        if not channel or not body:
            raise ToolValidationError(
                "channel and body are required", details={"channel": channel}
            )
        if source not in _VALID_SOURCES:
            raise ToolValidationError(
                f"unknown source '{source}'", details={"allowed": sorted(_VALID_SOURCES)}
            )
        self._require_permission(caller_id, "chat:write")
        ch = self._require_channel(channel)
        self._require_member(channel, caller_id)

        mentions = _MENTION_RE.findall(body)
        msg = self._store.add_message(
            channel_id=channel,
            sender_id=caller_id,
            body=body,                        # stored verbatim — never instructions
            source=source,
            trust_label=trust_label_for(source),
            mentions=mentions,
            correlation_id=ch["correlation_id"],
        )
        recipients = self._members(channel)          # authoritative delivered_to (cached)
        for agent_id in recipients:                   # active-state: track unread per recipient
            if agent_id != caller_id:
                self._cache.bump_unread(agent_id, channel)

        self._publisher.publish(
            ChatMessagePosted(
                event_type="chat.message_posted",
                actor_id=caller_id,
                sim_time=msg["sim_time"],
                seq=msg["seq"],
                channel=channel,
                message_id=msg["id"],
                mentions=mentions,
                trust_label=msg["trust_label"],
                correlation_id=ch["correlation_id"],
                recipients=recipients,
            )
        )
        return MessageReceipt(
            message_id=msg["id"],
            channel=channel,
            delivered_to=recipients,
            sent_at=datetime.fromisoformat(msg["sim_time"]),
        )

    def read_channel(self, caller_id: str, channel: str, since: int = 0) -> ChannelHistory:
        self._require_permission(caller_id, "chat:read")
        self._require_channel(channel)
        self._require_member(channel, caller_id)
        rows = self._store.messages_since(channel, since)
        messages = [
            ChatMessage(
                message_id=r["id"],
                seq=r["seq"],
                sender=r["sender_id"],
                body=r["body"],
                trust_label=r["trust_label"],
                mentions=r["mentions"],
                sent_at=datetime.fromisoformat(r["sim_time"]),
            )
            for r in rows
        ]
        next_cursor = messages[-1].seq if messages else since
        self._cache.reset_unread(caller_id, channel)   # caller has now seen this channel
        return ChannelHistory(channel=channel, messages=messages, next_cursor=next_cursor)

    def unread(self, caller_id: str) -> dict[str, int]:
        """Active-state read: this agent's unread count per channel (from the cache;
        empty when no cache is configured)."""
        self._require_permission(caller_id, "chat:read")
        return self._cache.unread(caller_id)

    def all_messages_since(self, caller_id: str, since: int = 0) -> list[dict]:
        """SYSTEM read: the cross-channel activation firehose the Director / coordinator
        polls to decide who wakes. Gated by `chat:system` (never granted to an agent
        role), so no agent — not even the CEO — can read across channels it isn't in
        (R8). Returns raw message rows (event plane), not a `ChatMessage` payload."""
        self._require_permission(caller_id, "chat:system")
        return self._store.all_messages_since(since)
