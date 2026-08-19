"""Employee → Internal Messaging System (v2), READ side, over REST.

Perception uses this to gather what the employee has seen: the channels it belongs
to and their new messages. The write side is the `SendChatMessage` tool
(`internal_messaging_adapter.py`); both share the same door and the same bound
identity, so "agents communicate through systems" (KB §1.8, §8) holds and the
model can never choose whose name a call goes out under.

Identity is the bound `agent_id`, injected as `Authorization: Bearer <agent_id>` —
never a call argument. `since` is the v2 monotonic `seq` cursor (an int), not a
timestamp. `http` is anything with `.get(url, headers, params)` returning a
response exposing `.status_code` and `.json()` (httpx.Client or a TestClient).
"""
from __future__ import annotations

from typing import Any


class ChatError(RuntimeError):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(f"internal_messaging {status}: {text}")
        self.status = status


class InternalMessagingClient:
    def __init__(self, http: Any, agent_id: str, base_url: str = "") -> None:
        self._http = http
        self._me = agent_id
        self._base = base_url.rstrip("/")

    @property
    def agent_id(self) -> str:
        return self._me

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._me}"}

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    @staticmethod
    def _raise_for(resp: Any) -> None:
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("error", {}).get("message") or str(resp.json())
            except Exception:  # noqa: BLE001
                msg = f"HTTP {resp.status_code}"
            raise ChatError(resp.status_code, msg)

    def list_channels(self) -> list[dict]:
        """The channels this agent is a member of. `id` is the channel id (perception
        keys on it), alongside type/name/correlation_id."""
        resp = self._http.get(self._url("/api/channels"), headers=self._headers)
        self._raise_for(resp)
        return [
            {
                "id": c["channel"],
                "type": c["type"],
                "name": c["name"],
                "correlation_id": c["correlation_id"],
            }
            for c in resp.json()["data"]["channels"]
        ]

    def fetch_history(self, channel_id: str, since: int = 0) -> list[dict]:
        """New messages in a channel (seq > `since`), oldest first. Field names are
        mapped to the perception-facing shape (id/sender_id/created_at) and each row
        carries its `seq` so the caller can advance the cursor."""
        resp = self._http.get(
            self._url(f"/api/channels/{channel_id}/messages"),
            headers=self._headers,
            params={"since": since},
        )
        self._raise_for(resp)
        return [
            {
                "id": m["message_id"],
                "seq": m["seq"],
                "sender_id": m["sender"],
                "body": m["body"],
                "trust_label": m["trust_label"],
                "mentions": m["mentions"],
                "created_at": m["sent_at"],
            }
            for m in resp.json()["data"]["messages"]
        ]
