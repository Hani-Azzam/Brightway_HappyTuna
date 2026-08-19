"""Core abstractions for MCP tools and clients.

This module defines the contracts every concrete tool and transport implements,
so the rest of the system depends on *interfaces*, not on any specific backing
service (internal chat, staff portal, audit, HTTP, ...). That keeps the agent's
domain logic testable and lets transports be swapped without touching callers.

The design encodes the repository's core rules:
- *Communicate through systems only*: an agent reaches the world exclusively via
  an :class:`MCPClient` / :class:`MCPTool`, never by calling another agent.
- *Authority is enforced*: every call carries a :class:`ToolContext` (identity +
  role), and every tool declares the permission it requires and whether it
  mutates state — the inputs an authorization guard needs.
- *Everything is auditable*: :class:`BaseTool` wraps each call with timing and
  uniform error capture so the result is always a fully-populated
  :class:`ToolResult`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .errors import MCPError, ToolNotFoundError
from .result import ResultMeta, ToolResult


class SideEffect(str, Enum):
    """Whether a tool only observes the world or changes it.

    ``WRITE`` tools are the ones an authorization guard and the audit log care
    most about, since they can move the simulation into an irreversible state.
    """

    READ = "READ"
    WRITE = "WRITE"


class ToolContext(BaseModel):
    """Per-call identity and tracing context.

    Supplies the inputs for the ``identity -> role -> state -> audit`` authority
    chain and ties a tool call to the originating request for replay.
    """

    model_config = ConfigDict(frozen=True)

    caller_id: str
    caller_role: str
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    trace_id: str | None = None
    idempotency_key: str | None = None
    deadline: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolSpec(BaseModel):
    """Declarative description of a tool.

    Used for discovery (an agent lists specs to decide what to call), for
    prompt construction, and for authorization (``required_permission`` /
    ``side_effect``). ``input_schema`` is a JSON Schema object describing the
    accepted arguments.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    side_effect: SideEffect = SideEffect.READ
    required_permission: str | None = None
    version: str = "1.0.0"


class MCPTool(ABC):
    """Contract for a single invocable tool."""

    @property
    @abstractmethod
    def spec(self) -> ToolSpec:
        """Static description of the tool (name, schema, authority needs)."""

    @abstractmethod
    async def invoke(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult[Any]:
        """Execute the tool and return a populated :class:`ToolResult`.

        Implementations should never raise across this boundary; failures are
        returned as a failed result. :class:`BaseTool` provides this guarantee.
        """


class BaseTool(MCPTool):
    """Template base that handles timing, metadata, and uniform error capture.

    Concrete tools implement only :meth:`_run` with their business logic and may
    raise :class:`MCPError`; this base converts the outcome into a
    :class:`ToolResult` with :class:`ResultMeta` attached. Unexpected exceptions
    are wrapped as ``INTERNAL`` so the tool boundary never leaks raw tracebacks
    to the agent loop.
    """

    async def invoke(self, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult[Any]:
        name = self.spec.name
        meta = ResultMeta(
            tool=name,
            idempotency_key=ctx.idempotency_key,
        )
        try:
            value = await self._run(dict(args), ctx)
            return ToolResult.success(name, value, meta=meta.finished())
        except MCPError as err:
            return ToolResult.from_exception(name, err, meta=meta.finished())
        except Exception as err:  # noqa: BLE001 - boundary: never leak raw errors
            wrapped = MCPError(
                f"Unexpected error in tool '{name}': {err}",
                details={"exception_type": type(err).__name__},
            )
            return ToolResult.from_exception(name, wrapped, meta=meta.finished())

    @abstractmethod
    async def _run(self, args: dict[str, Any], ctx: ToolContext) -> Any:
        """Tool business logic. Raise :class:`MCPError` on failure."""


class MCPClient(ABC):
    """Contract for a transport that exposes a set of tools.

    A client is how an agent reaches one backing system (or a bundle of them).
    Concrete clients may be in-process (:class:`LocalMCPClient`) or remote.
    """

    @abstractmethod
    async def list_tools(self) -> list[ToolSpec]:
        """Discover the tools this client exposes."""

    @abstractmethod
    async def call_tool(
        self, name: str, args: Mapping[str, Any], ctx: ToolContext
    ) -> ToolResult[Any]:
        """Invoke a named tool, returning a :class:`ToolResult`."""


class ToolRegistry:
    """In-memory registry mapping tool name -> :class:`MCPTool`.

    Backs :class:`LocalMCPClient` and any component that needs to look tools up
    by name (selectors, authorization, prompt builders).
    """

    def __init__(self, tools: list[MCPTool] | None = None) -> None:
        self._tools: dict[str, MCPTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: MCPTool) -> None:
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = tool

    def get(self, name: str) -> MCPTool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(
                f"No tool registered under name '{name}'",
                details={"name": name, "available": sorted(self._tools)},
            ) from None

    def has(self, name: str) -> bool:
        return name in self._tools

    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)


class LocalMCPClient(MCPClient):
    """Reference :class:`MCPClient` that invokes tools from a local registry.

    Used for in-process tools and tests; remote clients reuse the same contract
    so callers are transport-agnostic.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def list_tools(self) -> list[ToolSpec]:
        return self._registry.specs()

    async def call_tool(
        self, name: str, args: Mapping[str, Any], ctx: ToolContext
    ) -> ToolResult[Any]:
        try:
            tool = self._registry.get(name)
        except ToolNotFoundError as err:
            return ToolResult.from_exception(name, err, meta=ResultMeta(tool=name).finished())
        return await tool.invoke(args, ctx)
