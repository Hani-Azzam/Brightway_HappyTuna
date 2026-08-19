"""Employee → Customer Support system, via its REST API.

Support duty for employee personas: list the queue's open tickets and respond
to them. Same correctness rules as the chat adapter (`internal_messaging_adapter`):

- **Identity is bound at construction** (`employee_id`) and always injected as the
  ticket's `actor`/`assignee` — never an LLM-supplied argument, so the model
  cannot respond as someone else.
- **Writes set `is_idempotent=False`** so the ToolExecutor runs them exactly once.

`http` is any object with `.get`/`.patch` returning a response exposing
`.status_code` and `.json()` (httpx.Client or FastAPI TestClient).
"""
from __future__ import annotations

from typing import Any

from packages.agentkit.tool_base import ToolBase, ToolResult, ToolSchema


class _RestSupportTool(ToolBase):
    def __init__(self, http: Any, employee_id: str, base_url: str = "") -> None:
        self._http = http
        self._me = employee_id
        self._base = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    @staticmethod
    def _error_text(resp: Any) -> str:
        try:
            payload = resp.json()
            return payload.get("detail") or str(payload)
        except Exception:  # noqa: BLE001
            return f"HTTP {resp.status_code}"


class ListOpenTickets(_RestSupportTool):
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="list_open_tickets",
            description=(
                "List open customer support tickets (newest first). Use this to see "
                "which customer complaints are waiting for a response. Each ticket has "
                "a ticket_id, subject, description, issue_type, and priority."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "description": (
                            "Optional filter: quality, delivery, billing, general, "
                            "or safety_concern."
                        ),
                    },
                },
            },
        )

    def run(self, **kwargs) -> ToolResult:
        params: dict[str, str] = {"status": "open"}
        if kwargs.get("issue_type"):
            params["issue_type"] = kwargs["issue_type"]
        try:
            resp = self._http.get(self._url("/tickets"), params=params)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(error=f"customer support unreachable: {exc}", is_idempotent=True)
        if resp.status_code != 200:
            return ToolResult(error=self._error_text(resp), is_idempotent=True)

        tickets = resp.json()
        # Keep the observation compact: the fields an employee needs to triage.
        summary = [
            {
                "ticket_id": t.get("ticket_id"),
                "subject": t.get("subject"),
                "description": (t.get("description") or "")[:240],
                "issue_type": t.get("issue_type"),
                "priority": t.get("priority"),
                "customer_id": t.get("customer_id"),
                "sentiment": t.get("sentiment"),
            }
            for t in tickets[:10]
        ]
        return ToolResult(value={"count": len(tickets), "tickets": summary}, is_idempotent=True)


class RespondToTicket(_RestSupportTool):
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="respond_to_ticket",
            description=(
                "Reply to a customer support ticket and update its status. Use this to "
                "address a customer complaint: acknowledge the issue, say what the "
                "company is doing, and set the status ('in_progress' while working on "
                "it, 'resolved' when the answer settles it, 'escalated' for anything "
                "safety-critical you cannot settle yourself)."
            ),
            parameters={
                "type": "object",
                "required": ["ticket_id", "reply_message"],
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "The ticket to respond to, e.g. TCK-00042.",
                    },
                    "reply_message": {
                        "type": "string",
                        "description": "The reply sent to the customer, in your own words.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["in_progress", "escalated", "resolved"],
                        "description": "New ticket status. Defaults to in_progress.",
                    },
                },
            },
        )

    def run(self, **kwargs) -> ToolResult:
        body = {
            "reply_message": kwargs["reply_message"],
            "status": kwargs.get("status") or "in_progress",
            # Identity comes from the construction-time binding, never the model.
            "actor": self._me,
            "assignee": self._me,
        }
        try:
            resp = self._http.patch(self._url(f"/tickets/{kwargs['ticket_id']}"), json=body)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(error=f"customer support unreachable: {exc}", is_idempotent=False)
        if resp.status_code != 200:
            return ToolResult(error=self._error_text(resp), is_idempotent=False)
        t = resp.json()
        return ToolResult(
            value={
                "ticket_id": t.get("ticket_id"),
                "status": t.get("status"),
                "assignee": t.get("assignee"),
            },
            is_idempotent=False,
        )
