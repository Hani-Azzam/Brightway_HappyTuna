"""Typed error hierarchy for the MCP (tool) layer.

Every failure that crosses a tool boundary is represented either as a raised
:class:`MCPError` or as a serialized ``ErrorInfo`` carried inside a
:class:`~packages.mcp_core.result.ToolResult`. A single, typed hierarchy lets
callers branch on a stable :class:`ErrorCode` instead of parsing human strings,
and lets the immutable audit log record machine-readable codes that survive
replay.

Design rules honored here:
- *Authority is enforced*: authorization failures get their own code so the
  guardrail layer can reject a tool call before it ever runs.
- *Everything is auditable*: each error exposes ``code``/``details``/``retryable``
  so it can be flattened into an event payload without losing information.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class ErrorCode(str, Enum):
    """Stable, machine-readable failure categories for tool calls.

    Values are strings so they serialize cleanly into JSON audit events and can
    be compared without importing this module.
    """

    VALIDATION = "VALIDATION"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    EXECUTION = "EXECUTION"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    INTERNAL = "INTERNAL"


class MCPError(Exception):
    """Base class for every error raised inside the MCP tool layer.

    Concrete subclasses fix ``code`` and a sensible ``retryable`` default. The
    ``details`` mapping carries structured, non-sensitive context (argument
    names, limits, identifiers) that is safe to write to the audit log.
    """

    code: ErrorCode = ErrorCode.INTERNAL
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details) if details else {}
        if retryable is not None:
            self.retryable = retryable

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code.value!r}, "
            f"message={self.message!r}, retryable={self.retryable!r}, "
            f"details={self.details!r})"
        )


class ToolValidationError(MCPError):
    """Tool arguments failed schema or precondition validation."""

    code = ErrorCode.VALIDATION
    retryable = False


class ToolNotFoundError(MCPError):
    """No tool is registered under the requested name."""

    code = ErrorCode.NOT_FOUND
    retryable = False


class ToolAuthorizationError(MCPError):
    """The caller's identity/role is not permitted to invoke the tool."""

    code = ErrorCode.UNAUTHORIZED
    retryable = False


class ToolExecutionError(MCPError):
    """The tool ran but failed to produce a valid result."""

    code = ErrorCode.EXECUTION
    retryable = False


class ToolTimeoutError(MCPError):
    """The tool exceeded its deadline before completing."""

    code = ErrorCode.TIMEOUT
    retryable = True


class ToolUnavailableError(MCPError):
    """The backing system is temporarily unreachable."""

    code = ErrorCode.UNAVAILABLE
    retryable = True


class RateLimitError(MCPError):
    """The backing system rejected the call due to rate limiting."""

    code = ErrorCode.RATE_LIMITED
    retryable = True


class ToolConflictError(MCPError):
    """The call conflicts with current state (e.g., idempotency clash)."""

    code = ErrorCode.CONFLICT
    retryable = False
