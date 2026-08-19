"""Remote `MCPClient` — reach a tool service OVER HTTP.

The counterpart to `LocalMCPClient`: same `MCPClient` contract, different
transport, so an agent's tool code and orchestration do not change when a backing
system moves out of process (mcp_core's core promise). This is what lets the COO
run as its own service and still call `chat.send_message` — pointing here at the
Internal Messaging System's `/mcp/chat` endpoint instead of a local registry.

Identity is **bound** to the client (`agent_id`) and sent as the Bearer token;
the server derives the caller from it, so a request body can never impersonate
another agent. `http` is any object with sync `.get`/`.post` (httpx.Client or a
FastAPI TestClient).

Kept out of ``mcp_core.__init__`` so importing the core stays free of httpx.
"""
from __future__ import annotations

from typing import Any, Mapping

from .base import MCPClient, ToolContext, ToolSpec
from .errors import ToolUnavailableError
from .result import ResultMeta, ToolResult


class HttpMCPClient(MCPClient):
    def __init__(
        self,
        http: Any,
        agent_id: str,
        base_url: str = "",
        path: str = "/mcp/chat",
    ) -> None:
        self._http = http
        self._me = agent_id
        self._base = base_url.rstrip("/")
        self._path = path

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._me}"}

    def _url(self, suffix: str) -> str:
        return f"{self._base}{self._path}{suffix}"

    async def list_tools(self) -> list[ToolSpec]:
        resp = self._http.get(self._url("/tools"), headers=self._headers)
        return [ToolSpec.model_validate(s) for s in resp.json()["tools"]]

    async def call_tool(
        self, name: str, args: Mapping[str, Any], ctx: ToolContext | None = None
    ) -> ToolResult[Any]:
        # `ctx.caller_id` is intentionally NOT trusted for identity — the bound
        # agent_id (Bearer) is authoritative, mirroring the server.
        resp = self._http.post(
            self._url("/call"),
            headers=self._headers,
            json={"tool": name, "args": dict(args)},
        )
        if resp.status_code >= 500:
            return ToolResult.failure(
                name,
                ToolUnavailableError(f"chat transport error {resp.status_code}"),
                meta=ResultMeta(tool=name).finished(),
            )
        return ToolResult.model_validate(resp.json())
