"""Shared primitives for every domain schema.

Centralizes the small building blocks (base model config, id/time helpers,
the cross-cutting ``Severity`` scale, and ``ActorRef``) so the individual schema
modules stay DRY and consistent. Domain modules import from here; this module
imports nothing from its siblings, so there are no import cycles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp. Used everywhere for replayable ordering."""
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    """Generate a short, human-greppable id like ``crisis_3f9a...``.

    A typed prefix makes ids self-describing in logs and the audit trail.
    """
    return f"{prefix}_{uuid4().hex[:12]}"


class SchemaModel(BaseModel):
    """Base for all domain schemas.

    - ``extra='forbid'`` catches typos and stray fields at the boundary.
    - ``validate_assignment`` keeps mutable entities valid after status updates.
    - ``use_enum_values=False`` preserves enum types for ergonomic comparisons.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
    )


class Severity(str, Enum):
    """Cross-cutting severity scale shared by crises and risk levels."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        """Numeric ordering for thresholds/escalation (LOW=0 .. CRITICAL=3)."""
        return _SEVERITY_ORDER[self]


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MODERATE: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


class ActorRef(SchemaModel):
    """Immutable reference to an actor (who did/asked something).

    Carries the identity + role that the authority chain and audit log need,
    without embedding the actor's private state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: str
    role: str
    display_name: str | None = None
