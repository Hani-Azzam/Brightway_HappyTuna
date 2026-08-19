"""HTTP MCP transport — makes the `chat.*` tools reachable OVER THE WIRE.

Without this, the MCP door is `LocalMCPClient` (in-process only), so an
`mcp_core` agent could reach chat only if it ran inside the chat process. This
router exposes the same tools remotely, so the COO/CEO run as their own services
and reach chat exactly like the employee reaches the REST door — every agent is
independently deployable (KB Distributed Deployment).

Identity is the authenticated caller (Bearer = agent_id), resolved to a role via
the registry — never a field in the request body. So the anti-impersonation
guarantee holds across the wire too. The response is the raw `ToolResult`
envelope (ok/value/error/meta); a remote `MCPClient` reconstructs it.
"""
from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel

from packages.mcp_core import ToolContext
from packages.mcp_core.errors import ToolAuthorizationError
from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.transport.mcp.tools import build_chat_client


class _CallBody(BaseModel):
    tool: str
    args: dict = {}


def _caller_id(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise ToolAuthorizationError("missing or malformed bearer token")
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise ToolAuthorizationError("empty bearer token")
    return token


def build_mcp_router(service: InternalMessagingService) -> APIRouter:
    client = build_chat_client(service)          # the same in-process registry
    registry = service.registry
    router = APIRouter(prefix="/mcp/chat", tags=["mcp"])

    @router.get("/tools")
    async def list_tools() -> dict:
        specs = await client.list_tools()
        return {"tools": [s.model_dump(mode="json") for s in specs]}

    @router.post("/call")
    async def call_tool(body: _CallBody, authorization: str | None = Header(default=None)) -> dict:
        caller = _caller_id(authorization)       # identity from the connection, not the body
        ctx = ToolContext(caller_id=caller, caller_role=registry.role_of(caller))
        result = await client.call_tool(body.tool, body.args, ctx)
        return result.model_dump(mode="json")    # raw ToolResult envelope

    return router
