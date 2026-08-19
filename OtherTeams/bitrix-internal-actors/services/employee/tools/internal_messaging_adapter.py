"""Employee → Internal Messaging System, via the REST door.

The employee runs on `agentkit` (sync `ToolBase`), not `mcp_core`, so it reaches
chat over REST through this thin adapter rather than an MCP client. Two things
make it correct:

- **Identity is bound at construction** (`employee_id`) and injected as the
  Bearer token — it is NEVER an LLM-supplied argument, so the model cannot
  impersonate another agent (closes the `sender_id`-as-parameter gap).
- **Writes set `is_idempotent=False`** so the ToolExecutor runs them exactly once.

`http` is any object with `.post`/`.get` returning a response exposing
`.status_code` and `.json()` (httpx.Client or FastAPI TestClient).
"""
from __future__ import annotations

from typing import Any

from packages.agentkit.tool_base import ToolBase, ToolResult, ToolSchema


class _RestChatTool(ToolBase):
    def __init__(self, http: Any, employee_id: str, base_url: str = "") -> None:
        self._http = http
        self._me = employee_id
        self._base = base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._me}"}

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    @staticmethod
    def _error_text(resp: Any) -> str:
        try:
            payload = resp.json()
            return payload.get("error", {}).get("message") or str(payload)
        except Exception:  # noqa: BLE001
            return f"HTTP {resp.status_code}"


class SendChatMessage(_RestChatTool):
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="send_chat_message",
            description=(
                "Post a message to an internal-chat channel you belong to. "
                "Use @agent-id to mention someone."
            ),
            parameters={
                "type": "object",
                "required": ["channel", "body"],
                "properties": {
                    "channel": {"type": "string", "description": "The channel id to post to."},
                    "body": {"type": "string", "description": "The message text."},
                },
            },
        )

    def run(self, channel: str, body: str) -> ToolResult:
        resp = self._http.post(
            self._url(f"/api/channels/{channel}/messages"),
            headers=self._headers,
            json={"body": body},
        )
        if resp.status_code >= 400:
            return ToolResult(error=self._error_text(resp), is_idempotent=False)
        return ToolResult(value=resp.json()["data"], is_idempotent=False)  # write → once


class ReadChannel(_RestChatTool):
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_channel",
            description="Read messages from a channel you belong to; pass `since` (a seq) for new ones.",
            parameters={
                "type": "object",
                "required": ["channel"],
                "properties": {
                    "channel": {"type": "string"},
                    "since": {"type": "integer", "description": "Only messages with seq greater than this."},
                },
            },
        )

    def run(self, channel: str, since: int = 0) -> ToolResult:
        resp = self._http.get(
            self._url(f"/api/channels/{channel}/messages"),
            headers=self._headers,
            params={"since": since},
        )
        if resp.status_code >= 400:
            return ToolResult(error=self._error_text(resp), is_idempotent=True)
        return ToolResult(value=resp.json()["data"], is_idempotent=True)  # read → retryable
