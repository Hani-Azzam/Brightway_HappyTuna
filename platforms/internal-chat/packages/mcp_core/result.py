"""The standardized result envelope returned by every MCP tool call.

A :class:`ToolResult` is the *only* shape an agent ever receives back from a
tool. It is a discriminated success/failure container so callers never have to
guess whether they hold a value or an error, and it carries :class:`ResultMeta`
(timing, identifiers, attempt count) so each call can be appended to the
immutable audit log and reproduced from a seed.

Why a result object instead of raising?
- Tool calls cross a trust/process boundary; turning failures into *data* lets
  the orchestrator decide whether to retry, escalate, or report — without
  unwinding the call stack.
- The envelope is JSON-serializable end to end, which is what the audit/replay
  pipeline needs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Mapping, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .errors import ErrorCode, MCPError

T = TypeVar("T")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ErrorInfo(BaseModel):
    """Serializable snapshot of a failure, embedded in a failed result.

    Mirrors :class:`~packages.mcp_core.errors.MCPError` but as plain data so it
    can be stored, transmitted, and replayed without the original exception.
    """

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_exception(cls, err: MCPError) -> "ErrorInfo":
        return cls(
            code=err.code,
            message=err.message,
            retryable=err.retryable,
            details=dict(err.details),
        )

    def to_exception(self) -> MCPError:
        """Rebuild a raisable :class:`MCPError` from stored data."""
        exc = MCPError(self.message, details=self.details, retryable=self.retryable)
        exc.code = self.code
        return exc


class ResultMeta(BaseModel):
    """Provenance and timing for a single tool invocation.

    Captured for every call (success or failure) to support auditing, latency
    metrics, retry accounting, and deterministic replay.
    """

    model_config = ConfigDict(frozen=True)

    call_id: str = Field(default_factory=lambda: uuid4().hex)
    tool: str
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    duration_ms: float | None = None
    attempts: int = 1
    idempotency_key: str | None = None

    def finished(self, *, completed_at: datetime | None = None) -> "ResultMeta":
        """Return a copy stamped with completion time and computed duration."""
        end = completed_at or _utcnow()
        duration = (end - self.started_at).total_seconds() * 1000.0
        return self.model_copy(
            update={"completed_at": end, "duration_ms": round(duration, 3)}
        )


class ToolResult(BaseModel, Generic[T]):
    """Immutable success/failure envelope for a tool call.

    Use the :meth:`success` / :meth:`failure` / :meth:`from_exception` factories
    rather than constructing directly so the ``ok`` flag and the
    value/error invariant stay consistent.
    """

    model_config = ConfigDict(frozen=True)

    ok: bool
    tool: str
    value: T | None = None
    error: ErrorInfo | None = None
    meta: ResultMeta | None = None

    @classmethod
    def success(
        cls,
        tool: str,
        value: T,
        *,
        meta: ResultMeta | None = None,
    ) -> "ToolResult[T]":
        return cls(ok=True, tool=tool, value=value, error=None, meta=meta)

    @classmethod
    def failure(
        cls,
        tool: str,
        error: ErrorInfo | MCPError,
        *,
        meta: ResultMeta | None = None,
    ) -> "ToolResult[T]":
        info = error if isinstance(error, ErrorInfo) else ErrorInfo.from_exception(error)
        return cls(ok=False, tool=tool, value=None, error=info, meta=meta)

    @classmethod
    def from_exception(
        cls,
        tool: str,
        err: MCPError,
        *,
        meta: ResultMeta | None = None,
    ) -> "ToolResult[Any]":
        return cls.failure(tool, ErrorInfo.from_exception(err), meta=meta)

    @property
    def failed(self) -> bool:
        return not self.ok

    def unwrap(self) -> T:
        """Return the value on success, or re-raise the stored error.

        Lets call sites that genuinely cannot proceed without a value convert a
        failed result back into an exception at a single, explicit point.
        """
        if self.ok:
            return self.value  # type: ignore[return-value]
        if self.error is not None:
            raise self.error.to_exception()
        raise MCPError("Tool result is not ok but carries no error", details={"tool": self.tool})

    def map_meta(self, meta: ResultMeta) -> "ToolResult[T]":
        """Return a copy with ``meta`` attached (used by the invocation wrapper)."""
        return self.model_copy(update={"meta": meta})
