"""Builds the unified, namespaced tool catalog from the live sessions.

The namespace is mandatory, not cosmetic: `search`, `get_post`, and
`get_hashtag_posts` each exist on both the social and analytics servers with
different signatures, so a flat namespace would silently route a call to whichever
server was registered last.

Tool metadata is passed through exactly as the servers report it. The one thing
this module adds is `access`, from `TOOL_ACCESS` below.
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping

from mcp import ClientSession
from mcp.types import PaginatedRequestParams

from .models import AccessLevel, ToolEntry

logger = logging.getLogger(__name__)

#: Stops a misbehaving server from paging forever. All three return their whole
#: tool list in one response today.
MAX_TOOL_PAGES = 20


class CatalogError(RuntimeError):
    """The live tool set and the classification table disagree.

    Raised, never warned. An unclassified tool means a server grew a capability
    nobody has assessed the blast radius of, and the gateway is the layer meant to
    make that impossible to miss.
    """


# Hand-maintained on purpose. Every entry is a decision about what the tool does
# to the world, made by reading that tool's implementation -- never inferred from
# its name, and never defaulted. Name inference would fail on the two that matter
# most: run_analysis reads like a query but overwrites the stored sentiment the
# CEO is scored against, and login reads like setup but rebinds the session
# identity, re-authoring every later write.
TOOL_ACCESS: dict[str, dict[str, AccessLevel]] = {
    # Customer_Support_System/mcp_server.py
    "support": {
        "create_ticket": "write",
        "patch_ticket": "write",
        "get_ticket": "read",
        "list_tickets": "read",
        "get_activity_log": "read",
    },
    # social_network/src/mcp/analyticsServer.ts
    "analytics": {
        # Recomputes and overwrites stored per-post sentiment. Not a read.
        "run_analysis": "write",
        # Flips the sentiment engine at runtime, changing how every later number
        # here is produced. Simulation-operator control, not a read.
        "set_ai_analysis": "write",
        "get_overview": "read",
        "get_sentiment_timeline": "read",
        "get_aspect_sentiment": "read",
        "get_trends": "read",
        "get_top_influencers": "read",
        "detect_spikes": "read",
        "get_cohort_sentiment": "read",
        "get_narratives": "read",
        "get_top_posts": "read",
        "get_analysis_status": "read",
        "search": "read",
        "get_post": "read",
        "get_hashtag_posts": "read",
    },
    # social_network/src/mcp/socialServer.ts
    "social": {
        # The only two writes in the catalog with no inverse anywhere: public the
        # moment they land, and no server exposes a tool that deletes either.
        # Contrast the engagement writes below, which all pair with an undo.
        "create_post": "public_write",
        "add_comment": "public_write",
        # Rebinds this session's identity, re-authoring every subsequent write.
        "login": "write",
        # Moves the agent between analytics cohorts, changing what
        # analytics.get_cohort_sentiment reports about the company's own voice.
        "set_account_type": "write",
        "like_post": "write",
        "unlike_post": "write",
        "repost_post": "write",
        "unrepost_post": "write",
        "follow_user": "write",
        "unfollow_user": "write",
        "get_meta": "read",
        "get_my_feed": "read",
        "get_global_feed": "read",
        "list_users": "read",
        "get_user": "read",
        "get_user_posts": "read",
        "get_following": "read",
        "get_post": "read",
        "get_comments": "read",
        "search": "read",
        "get_trending_hashtags": "read",
        "get_hashtag_posts": "read",
    },
    # internal-messaging-mcp (bitrix-internal-messaging), served at /mcp
    "chat": {
        # Same shape as social.login: binds this session to an agent identity, so
        # every later call is authored by whoever it named. Connection-layer,
        # owned by connection.py, denied to the role in roles.yaml.
        "login": "write",
        # Writes, but internal ones -- these land in the company's own chat, not
        # on the public timeline, and none of them is visible to the simulated
        # public. That is why they are "write" and not "public_write": the
        # distinction in this table is blast radius, not reversibility.
        "send_message": "write",
        "create_channel": "write",
        "add_member": "write",
        "list_channels": "read",
        "read_channel": "read",
    },
}


def qualify(server_id: str, tool_name: str) -> str:
    """Builds the catalog key for a tool. The one place this format is defined."""
    return f"{server_id}.{tool_name}"


class Catalog:
    """The namespaced tool catalog: every tool on every connected server.

    Read-only once built. Deliberately offers no filtering by role -- that is
    `policy.py`'s job, and putting it here would give callers a second, unpoliced
    way to reach the tool set.
    """

    def __init__(self, entries: Iterable[ToolEntry]) -> None:
        self._entries: dict[str, ToolEntry] = {}
        for entry in entries:
            self._entries[entry.qualified_name] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, qualified_name: object) -> bool:
        return qualified_name in self._entries

    def __iter__(self):
        return iter(self._entries.values())

    def get(self, qualified_name: str) -> ToolEntry | None:
        """The entry for a qualified name, or None if the catalog has no such tool."""
        return self._entries.get(qualified_name)

    def all(self) -> list[ToolEntry]:
        """Every entry, in the order the servers reported them."""
        return list(self._entries.values())

    @property
    def server_ids(self) -> list[str]:
        """Server ids present in the catalog, in first-seen order."""
        seen: list[str] = []
        for entry in self._entries.values():
            if entry.server_id not in seen:
                seen.append(entry.server_id)
        return seen

    def for_server(self, server_id: str) -> list[ToolEntry]:
        """Every entry belonging to one server."""
        return [e for e in self._entries.values() if e.server_id == server_id]

    def by_access(self, access: AccessLevel) -> list[ToolEntry]:
        """Every entry at one access level."""
        return [e for e in self._entries.values() if e.access == access]

    def access_counts(self) -> dict[str, int]:
        """How many tools sit at each access level, for reporting."""
        counts: dict[str, int] = {"read": 0, "write": 0, "public_write": 0}
        for entry in self._entries.values():
            counts[entry.access] = counts.get(entry.access, 0) + 1
        return counts


async def _list_all_tools(session: ClientSession) -> list:
    """Lists a server's tools, following `nextCursor` if it pages."""
    tools: list = []
    cursor: str | None = None

    for _ in range(MAX_TOOL_PAGES):
        # params=, not the deprecated cursor= keyword.
        result = await session.list_tools(params=PaginatedRequestParams(cursor=cursor))
        tools.extend(result.tools)
        cursor = result.nextCursor
        if not cursor:
            return tools

    logger.warning(
        "Stopped listing tools after %d pages; the server may be paging endlessly.",
        MAX_TOOL_PAGES,
    )
    return tools


def _classify(server_id: str, tool_names: Iterable[str]) -> dict[str, AccessLevel]:
    """Looks up every tool's access level, raising if any is unclassified.

    Also warns about the opposite drift -- a tool in the table that the server no
    longer serves -- which usually means a rename or a removal worth noticing.
    """
    server_table = TOOL_ACCESS.get(server_id)
    if server_table is None:
        raise CatalogError(
            f"Server {server_id!r} has no entry in TOOL_ACCESS (gateway/catalog.py). "
            f"Every server in mcp_servers.yaml needs a classification table; add "
            f"{server_id!r} with one entry per tool it serves."
        )

    live_names = list(tool_names)
    unclassified = [name for name in live_names if name not in server_table]
    if unclassified:
        listed = "\n".join(f'    "{name}": "read",  # <- decide: read | write | public_write'
                           for name in sorted(unclassified))
        raise CatalogError(
            f"{len(unclassified)} tool(s) on server {server_id!r} are missing from "
            f"TOOL_ACCESS (gateway/catalog.py): {', '.join(sorted(unclassified))}.\n"
            f"This means that team added or renamed a tool. Read what it actually does, "
            f"then add it to TOOL_ACCESS[{server_id!r}]:\n{listed}\n"
            f"Unclassified tools are never defaulted -- an unassessed capability must not "
            f"reach the agent by accident."
        )

    stale = [name for name in server_table if name not in live_names]
    if stale:
        logger.warning(
            "TOOL_ACCESS[%r] classifies %d tool(s) the server no longer serves: %s. "
            "Likely renamed or removed upstream; the entries are now dead.",
            server_id,
            len(stale),
            ", ".join(sorted(stale)),
        )

    return {name: server_table[name] for name in live_names}


async def build_catalog(sessions: Mapping[str, ClientSession]) -> Catalog:
    """Builds the catalog from live sessions, keyed by server id.

    Pass `GatewayConnections.sessions` -- only servers that actually connected
    appear, so a skipped server yields a smaller catalog rather than an error.

    Raises `CatalogError` if any live tool is missing from `TOOL_ACCESS`.
    """
    entries: list[ToolEntry] = []

    for server_id, session in sessions.items():
        tools = await _list_all_tools(session)
        access_by_name = _classify(server_id, (tool.name for tool in tools))

        for tool in tools:
            entries.append(
                ToolEntry(
                    qualified_name=qualify(server_id, tool.name),
                    server_id=server_id,
                    tool_name=tool.name,
                    access=access_by_name[tool.name],
                    title=tool.title,
                    description=tool.description,
                    input_schema=tool.inputSchema or {},
                )
            )

        logger.info("Catalogued %d tool(s) from %r", len(tools), server_id)

    catalog = Catalog(entries)
    counts = catalog.access_counts()
    logger.info(
        "Catalog built: %d tool(s) across %d server(s) -- %d read, %d write, %d public_write",
        len(catalog),
        len(catalog.server_ids),
        counts["read"],
        counts["write"],
        counts["public_write"],
    )
    return catalog
