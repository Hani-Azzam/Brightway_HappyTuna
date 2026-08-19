from enum import Enum
from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel


class TicketStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    escalated = "escalated"
    resolved = "resolved"
    closed = "closed"


class TicketPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IssueType(str, Enum):
    quality = "quality"
    delivery = "delivery"
    billing = "billing"
    general = "general"
    safety_concern = "safety_concern"


class Sentiment(str, Enum):
    angry = "angry"
    frustrated = "frustrated"
    neutral = "neutral"
    positive = "positive"


class Ticket(BaseModel):
    ticket_id: str
    customer_id: str
    created_at: datetime
    updated_at: datetime
    status: TicketStatus
    priority: TicketPriority
    issue_type: IssueType
    subject: str
    description: str
    linked_product_batch: Optional[str] = None
    sentiment: Optional[Sentiment] = None
    sentiment_method: Optional[str] = None
    assignee: Optional[str] = None
    reply_message: Optional[str] = None
    schema_version: int = 1


class TicketCreate(BaseModel):
    customer_id: str
    issue_type: IssueType
    subject: str
    description: str
    linked_product_batch: Optional[str] = None
    priority: TicketPriority = TicketPriority.medium


class TicketPatch(BaseModel):
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    sentiment: Optional[Sentiment] = None
    sentiment_method: Optional[str] = None
    assignee: Optional[str] = None
    reply_message: Optional[str] = None
    actor: Optional[str] = None


class ActivityLogEntry(BaseModel):
    log_id: str
    entity_type: str
    entity_id: str
    activity_type: str
    timestamp: datetime
    actor: str
    details: dict[str, Any] = {}
    schema_version: int = 1
