"""Tool: send a BitriX Mail message as this employee.

PROVISIONAL — the BitriX Mail service API is not finalized (see technical-design
open question #4). Assumed contract:

    POST {mail_url}/messages
      headers: X-Agent-Id: <employee_id>
      json:    {"to": [str], "subject": str, "body": str}
    -> 201 {"id": ...}

The tool shape is stable; only the endpoint/contract may change when Team 3 ships
the real service. Sending is a WRITE → `is_idempotent=False`.
"""
from __future__ import annotations

import httpx

from packages.agentkit.tool_base import ToolBase, ToolResult, ToolSchema


class MailSendTool(ToolBase):
    def __init__(
        self,
        base_url: str,
        agent_id: str,
        *,
        http: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._agent_id = agent_id
        self._http = http or httpx.Client(base_url=self._base_url, timeout=10.0)

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="send_mail",
            description=(
                "Send an email to one or more recipients. Use for formal or external "
                "communication that does not belong in a chat channel."
            ),
            parameters={
                "type": "object",
                "required": ["to", "subject", "body"],
                "properties": {
                    "to": {"type": "array", "description": "recipient agent ids or addresses"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        )

    def run(self, to: list[str], subject: str, body: str) -> ToolResult:
        try:
            resp = self._http.post(
                "/messages",
                headers={"X-Agent-Id": self._agent_id},
                json={"to": to, "subject": subject, "body": body},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(error=f"mail send failed: {exc}", is_idempotent=False)
        if resp.status_code in (200, 201):
            return ToolResult(value=resp.json(), is_idempotent=False)
        return ToolResult(error=f"mail send failed: {resp.status_code} {resp.text}",
                          is_idempotent=False)
