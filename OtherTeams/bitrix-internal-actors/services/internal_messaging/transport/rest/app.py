"""REST face — the framework-neutral door (cross-language agents, the employee's
agentkit adapter, the Director, polling).

Thin handlers: resolve identity from the Bearer token, call the one service, and
shape the `{success, data?, error?}` envelope (social-network convention). A
service `MCPError` is mapped to an HTTP status by a single exception handler, so
REST and MCP enforce identical rules.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from packages.mcp_core.errors import ErrorCode, MCPError, ToolAuthorizationError
from services.internal_messaging.domain.service import InternalMessagingService

_STATUS_BY_CODE = {
    ErrorCode.VALIDATION: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.UNAUTHORIZED: 403,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.TIMEOUT: 504,
    ErrorCode.UNAVAILABLE: 503,
}


def _caller_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise ToolAuthorizationError("missing or malformed bearer token")
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise ToolAuthorizationError("empty bearer token")
    return token


def _ok(payload: Any) -> JSONResponse:
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    return JSONResponse(content={"success": True, "data": data})


class _CreateChannelBody(BaseModel):
    type: str
    members: list[str] = []
    name: str | None = None
    correlation_id: str | None = None


class _AddMemberBody(BaseModel):
    agent_id: str
    role: str = "member"


class _MessageBody(BaseModel):
    body: str
    to: list[str] | None = None
    source: str = "internal"


def build_router(service: InternalMessagingService) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/channels")
    def create_channel(body: _CreateChannelBody, caller: str = Depends(_caller_id)) -> JSONResponse:
        return _ok(
            service.create_channel(
                caller_id=caller,
                channel_type=body.type,
                members=body.members,
                name=body.name,
                correlation_id=body.correlation_id,
            )
        )

    @router.get("/channels")
    def list_channels(caller: str = Depends(_caller_id)) -> JSONResponse:
        return _ok(service.list_channels(caller_id=caller))

    @router.post("/channels/{channel}/members")
    def add_member(
        channel: str, body: _AddMemberBody, caller: str = Depends(_caller_id)
    ) -> JSONResponse:
        return _ok(
            service.add_member(
                caller_id=caller, channel=channel, agent_id=body.agent_id, role=body.role
            )
        )

    @router.post("/channels/{channel}/messages")
    def send_message(
        channel: str, body: _MessageBody, caller: str = Depends(_caller_id)
    ) -> JSONResponse:
        return _ok(
            service.send_message(
                caller_id=caller,
                channel=channel,
                body=body.body,
                to=body.to,
                source=body.source,
            )
        )

    @router.get("/channels/{channel}/messages")
    def read_channel(
        channel: str, since: int = Query(default=0), caller: str = Depends(_caller_id)
    ) -> JSONResponse:
        return _ok(service.read_channel(caller_id=caller, channel=channel, since=since))

    @router.get("/messages")
    def all_messages(
        since: int = Query(default=0), caller: str = Depends(_caller_id)
    ) -> JSONResponse:
        # Cross-channel firehose for the activation layer (needs chat:system).
        rows = service.all_messages_since(caller_id=caller, since=since)
        next_cursor = rows[-1]["seq"] if rows else since
        return _ok({"messages": rows, "next_cursor": next_cursor})

    @router.get("/unread")
    def unread(caller: str = Depends(_caller_id)) -> JSONResponse:
        # Active-state read (Redis-backed): unread count per channel for this agent.
        return _ok({"unread": service.unread(caller_id=caller)})

    return router


def create_rest_app(service: InternalMessagingService) -> FastAPI:
    app = FastAPI(title="Internal Messaging System", version="1.0.0")

    @app.exception_handler(MCPError)
    async def _on_mcp_error(_req, exc: MCPError) -> JSONResponse:  # type: ignore[no-untyped-def]
        status = _STATUS_BY_CODE.get(exc.code, 500)
        return JSONResponse(
            status_code=status,
            content={"success": False, "error": {"code": exc.code.value, "message": exc.message}},
        )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(build_router(service))          # REST door
    # MCP door over HTTP (remote mcp_core agents: COO/CEO). Lazy import avoids a
    # module cycle (http.py -> tools -> service).
    from services.internal_messaging.transport.mcp.http import build_mcp_router

    app.include_router(build_mcp_router(service))
    return app
