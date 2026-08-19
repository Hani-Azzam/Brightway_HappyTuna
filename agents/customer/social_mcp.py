"""Customer -> Social Network, over the platform's MCP server.

Used by register.py when a persona's decision is to speak publicly
(complain_on_social_media / recommend_company): the persona logs in under its
own display name and publishes a real post on BrightTweets.

Deliberately a direct MCP client rather than a NAT `mcp_client` function group:
the social server binds identity to the MCP *session* (its `login` tool stores
the user on per-session state, and `create_post` 401s without it), so login and
create_post must run on the same session, and different personas must never
share one. Opening a short-lived session per post makes both guarantees
trivially true; a shared function-group session would make identity depend on
NAT's connection pooling behavior.

The `mcp` package is already a dependency of nvidia-nat-mcp.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_URL = os.environ.get("SOCIAL_NETWORK_MCP_URL", "http://social-network:3000/mcp/social")

#: The platform rejects longer posts (max 500 chars).
MAX_POST_CHARS = 500

_TIMEOUT = timedelta(seconds=20)


def _payload(result) -> dict:
    """The JSON body of a tool result, or a diagnostic dict."""
    texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    text = "\n".join(texts)
    if result.isError:
        raise RuntimeError(text or "social network tool call failed")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"raw": text}


async def create_post_as(persona_name: str, content: str, url: str | None = None) -> dict:
    """Log in as `persona_name` (auto-registers on first use) and publish `content`.

    Returns the created post's data (id, content, ...). Raises on failure --
    the caller decides whether a failed post should fail the whole decision.
    """
    content = content.strip()
    if len(content) > MAX_POST_CHARS:
        content = content[: MAX_POST_CHARS - 3] + "..."

    async with streamablehttp_client(url or DEFAULT_URL, timeout=_TIMEOUT) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            _payload(await session.call_tool("login", {"name": persona_name}))
            post = _payload(await session.call_tool("create_post", {"content": content}))
            return post
