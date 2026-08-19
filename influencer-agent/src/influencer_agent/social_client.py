"""The only module in this service allowed to talk to social_network.

Every call goes through its public HTTP API (never Prisma, never the database file) so the
two services stay fully independent, as required. All responses use social_network's
standard envelope: {"success": bool, "data"?: T, "error"?: str}.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SocialNetworkError(RuntimeError):
    """Raised when social_network returns success: false or a non-2xx status."""


@dataclass
class BotIdentity:
    user_id: str
    token: str
    name: str


class SocialNetworkClient:
    """Async client for the subset of the social_network REST API the influencer agent needs."""

    def __init__(self, base_url: str, timeout_seconds: float = 15.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SocialNetworkClient":
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.aclose()

    def _unwrap(self, response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError as exc:
            raise SocialNetworkError(f"Non-JSON response from social_network ({response.status_code})") from exc

        if response.status_code >= 400 or not body.get("success", False):
            error = body.get("error", f"HTTP {response.status_code}")
            raise SocialNetworkError(f"social_network request failed: {error}")

        return body.get("data")

    async def login_or_create_bot(self, name: str, account_type: str) -> BotIdentity:
        """Logs the persona in (name-only auth upserts the user), then ensures its accountType."""
        response = await self._client.post("/api/auth/login", json={"name": name})
        data = self._unwrap(response)
        token, user = data["token"], data["user"]

        if user.get("accountType") != account_type:
            patch_response = await self._client.patch(
                f"/api/users/{user['id']}",
                json={"accountType": account_type},
                headers={"Authorization": f"Bearer {token}"},
            )
            self._unwrap(patch_response)

        return BotIdentity(user_id=user["id"], token=token, name=user["name"])

    async def get_feed_page(self, page: int, limit: int) -> list[dict[str, Any]]:
        """One page of the global feed, newest post first."""
        response = await self._client.get("/api/posts", params={"page": page, "limit": limit})
        data = self._unwrap(response)
        return data["posts"]

    async def post_comment(self, post_id: str, token: str, content: str) -> dict[str, Any]:
        response = await self._client.post(
            f"/api/posts/{post_id}/comments",
            json={"content": content},
            headers={"Authorization": f"Bearer {token}"},
        )
        data = self._unwrap(response)
        return data["comment"]

    async def repost(self, post_id: str, token: str) -> None:
        response = await self._client.post(
            f"/api/posts/{post_id}/repost",
            headers={"Authorization": f"Bearer {token}"},
        )
        self._unwrap(response)
