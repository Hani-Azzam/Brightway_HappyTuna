"""MCP Core: the foundational tool-call layer for the internal-org agents.

Public API for the Model-Context-Protocol primitives every agent and service
uses to call world tools in a uniform, auditable, authority-checked way.

Layering (low -> high):
    errors  -> result -> base

Nothing here imports domain schemas or any concrete backing service, so this
package stays a stable foundation the rest of the codebase builds on.
"""

from __future__ import annotations

from .base import (
    BaseTool,
    LocalMCPClient,
    MCPClient,
    MCPTool,
    SideEffect,
    ToolContext,
    ToolRegistry,
    ToolSpec,
)
from .errors import (
    ErrorCode,
    MCPError,
    RateLimitError,
    ToolAuthorizationError,
    ToolConflictError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolTimeoutError,
    ToolUnavailableError,
    ToolValidationError,
)
from .result import ErrorInfo, ResultMeta, ToolResult

__all__ = [
    # errors
    "ErrorCode",
    "MCPError",
    "ToolValidationError",
    "ToolNotFoundError",
    "ToolAuthorizationError",
    "ToolExecutionError",
    "ToolTimeoutError",
    "ToolUnavailableError",
    "RateLimitError",
    "ToolConflictError",
    # result
    "ErrorInfo",
    "ResultMeta",
    "ToolResult",
    # base
    "SideEffect",
    "ToolContext",
    "ToolSpec",
    "MCPTool",
    "BaseTool",
    "MCPClient",
    "ToolRegistry",
    "LocalMCPClient",
]
