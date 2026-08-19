"""Typed payloads carried inside an MCP :class:`~mcp_core.ToolResult`.

The generic ``ToolResult[T]`` envelope (Sprint 3) stays domain-agnostic; this
module supplies the concrete ``T`` payloads for the internal-org systems the COO
talks to (internal chat, staff portal, audit, quality lab). The type aliases at
the bottom give call sites precise return types, e.g. ``ChatToolResult``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from packages.mcp_core import ToolResult

from .base import SchemaModel, utcnow


class MessageReceipt(SchemaModel):
    """Confirmation that an internal-chat message was delivered."""

    message_id: str
    channel: str
    delivered_to: list[str] = Field(default_factory=list)
    sent_at: datetime = Field(default_factory=utcnow)


class AnnouncementReceipt(SchemaModel):
    """Confirmation that a staff-portal announcement was posted."""

    announcement_id: str
    portal: str = "staff_portal"
    audience_size: int = Field(default=0, ge=0)
    posted_at: datetime = Field(default_factory=utcnow)


class AuditAck(SchemaModel):
    """Acknowledgement that an event was appended to the immutable audit log."""

    event_id: str
    sequence: int = Field(ge=0)
    recorded_at: datetime = Field(default_factory=utcnow)


class LabTestOutcome(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    INCONCLUSIVE = "INCONCLUSIVE"


class LabReport(SchemaModel):
    """Result payload returned by the quality-lab tool."""

    report_id: str
    production_line: str
    pathogen: str
    outcome: LabTestOutcome
    sampled_at: datetime
    notes: str | None = None


class StatusSnapshot(SchemaModel):
    """A point-in-time operational status read used in COO status reports."""

    captured_at: datetime = Field(default_factory=utcnow)
    line_status: dict[str, str] = Field(default_factory=dict)
    open_incidents: int = Field(default=0, ge=0)
    pending_approvals: int = Field(default=0, ge=0)
    metrics: dict[str, float] = Field(default_factory=dict)


class InventorySnapshot(SchemaModel):
    """Stock position for a SKU, returned by the inventory tool."""

    sku: str
    on_hand_units: int = Field(default=0, ge=0)
    in_transit_units: int = Field(default=0, ge=0)
    warehouses: dict[str, int] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=utcnow)


class BatchTraceResult(SchemaModel):
    """Mapping of a batch id to its production line and downstream shipments."""

    batch_id: str
    production_line: str | None = None
    produced_at: datetime | None = None
    shipped_to: list[str] = Field(default_factory=list)
    affected_skus: list[str] = Field(default_factory=list)
    units_estimated: int | None = Field(default=None, ge=0)


# --- Internal-chat READ payloads (added for the Internal Messaging System) ---
# The COO contract defines the WRITE side (MessageReceipt) but no read/history
# payload. These fill that gap so an agent can read a channel it belongs to.


class ChatMessage(SchemaModel):
    """One message as returned when reading a channel."""

    message_id: str
    seq: int = Field(ge=0)          # monotonic order cursor
    sender: str
    body: str                        # stored verbatim; never treated as instructions
    trust_label: str                 # internal | external | untrusted
    mentions: list[str] = Field(default_factory=list)
    sent_at: datetime = Field(default_factory=utcnow)


class ChannelHistory(SchemaModel):
    """A page of a channel's messages, oldest first."""

    channel: str
    messages: list[ChatMessage] = Field(default_factory=list)
    next_cursor: int = Field(default=0, ge=0)   # pass back as `since` for only newer messages


class ChannelSummary(SchemaModel):
    """Lightweight channel descriptor for listing."""

    channel: str
    type: str                        # direct | group | incident
    name: str | None = None
    correlation_id: str | None = None
    member_count: int = Field(default=0, ge=0)


class ChannelList(SchemaModel):
    """The channels a caller belongs to."""

    channels: list[ChannelSummary] = Field(default_factory=list)


class ChannelReceipt(SchemaModel):
    """Confirmation that a channel was created."""

    channel: str
    type: str
    created_at: datetime = Field(default_factory=utcnow)


class MembershipAck(SchemaModel):
    """Confirmation that a member was added to a channel."""

    channel: str
    agent_id: str
    role: str = "member"


# Precise result types for each system call (envelope + domain payload).
ChatToolResult = ToolResult[MessageReceipt]
ChannelHistoryResult = ToolResult[ChannelHistory]
ChannelListResult = ToolResult[ChannelList]
ChannelReceiptResult = ToolResult[ChannelReceipt]
MembershipAckResult = ToolResult[MembershipAck]
PortalToolResult = ToolResult[AnnouncementReceipt]
AuditToolResult = ToolResult[AuditAck]
LabToolResult = ToolResult[LabReport]
StatusToolResult = ToolResult[StatusSnapshot]
InventoryToolResult = ToolResult[InventorySnapshot]
BatchTraceToolResult = ToolResult[BatchTraceResult]
