"""Tool: update an Employee Portal task as this employee.

PROVISIONAL — the Employee Portal API is not finalized (technical-design open
question #4). Assumed contract:

    POST {portal_url}/tasks/{task_id}/updates
      json: {"agent_id": str, "status": str, "note": str}
    -> 200/201 {"task_id": ..., "status": ...}

Updating a task is a WRITE → `is_idempotent=False`.
"""
from __future__ import annotations

import httpx

from packages.agentkit.tool_base import ToolBase, ToolResult, ToolSchema

_STATUSES = ["acknowledged", "in_progress", "blocked", "done"]


class PortalTaskUpdateTool(ToolBase):
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
            name="update_task",
            description="Update the status of a work task assigned to you on the Employee Portal.",
            parameters={
                "type": "object",
                "required": ["task_id", "status"],
                "properties": {
                    "task_id": {"type": "string"},
                    "status": {"type": "string", "enum": _STATUSES},
                    "note": {"type": "string", "description": "optional progress note"},
                },
            },
        )

    def run(self, task_id: str, status: str, note: str = "") -> ToolResult:
        try:
            resp = self._http.post(
                f"/tasks/{task_id}/updates",
                json={"agent_id": self._agent_id, "status": status, "note": note},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(error=f"task update failed: {exc}", is_idempotent=False)
        if resp.status_code in (200, 201):
            return ToolResult(value=resp.json(), is_idempotent=False)
        return ToolResult(error=f"task update failed: {resp.status_code} {resp.text}",
                          is_idempotent=False)
