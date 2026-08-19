"""The coordinator's window onto chat: the Internal Messaging System's firehose.

The coordinator is the activation layer (the "Director"), so it reads ACROSS all
channels — a privilege no agent has. It gets that through the service's
`chat:system`-gated `all_messages_since`, wrapped here behind a tiny seam so the
watcher doesn't care whether the service is in-process (sim) or reached over REST
(`GET /api/messages?since=`) later. Only the source of events changes; routing,
activation, and logging stay identical.
"""
from __future__ import annotations

from typing import Any, Protocol


class MessageReader(Protocol):
    def all_messages_since(self, since: int) -> list[dict]: ...


class ServiceMessageReader:
    """In-process reader over the internal_messaging service. `caller_id` must be a
    registered `system`/`coordinator` identity (has `chat:system`)."""

    def __init__(self, service: Any, caller_id: str) -> None:
        self._service = service
        self._caller = caller_id

    def all_messages_since(self, since: int) -> list[dict]:
        return self._service.all_messages_since(self._caller, since)


class RestMessageReader:
    """Reader over the messaging service's REST firehose (`GET /api/messages?since=`).

    Used when the coordinator runs in a different process from the messaging service
    (the distributed-deployment case) — e.g. embedded in the employee worker reaching
    the service over the wire. Identity is the Bearer token, so it must resolve to a
    `chat:system` role. `http` is anything with `.get(url, headers, params)`."""

    def __init__(self, http: Any, base_url: str, caller_id: str) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self._caller = caller_id

    def all_messages_since(self, since: int) -> list[dict]:
        resp = self._http.get(
            f"{self._base}/api/messages",
            headers={"Authorization": f"Bearer {self._caller}"},
            params={"since": since},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"firehose read failed: HTTP {resp.status_code}")
        return resp.json()["data"]["messages"]
