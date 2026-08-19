"""Domain vocabulary for the Internal Messaging System.

Plain enums/constants only — no persistence, no framework. The store speaks in
dicts; the service maps those to the shared `packages.schemas` payloads.
"""
from __future__ import annotations

from enum import Enum


class ChannelType(str, Enum):
    """The channel kinds this system owns.

    Announcements are deliberately absent — those are the Staff Portal's job
    (`portal.post_announcement`), per the COO contract.
    """

    DIRECT = "direct"        # exactly 2 members, 1:1
    GROUP = "group"          # multi-party room
    INCIDENT = "incident"    # crisis room; carries a correlation_id


class MemberRole(str, Enum):
    OWNER = "owner"          # creator; may add members
    MEMBER = "member"


# Trust labels applied to a message body by source (KB §4.3/§4.4). The body is
# always stored verbatim as data; the label tells a consuming agent how much to
# trust it. Chat labels, it never sanitizes.
TRUST_BY_SOURCE: dict[str, str] = {
    "internal": "internal",
    "external": "external",
    "anonymous": "untrusted",
}


def trust_label_for(source: str) -> str:
    return TRUST_BY_SOURCE.get(source, "untrusted")


# Coarse default permission policy (KB §4.1). The hard isolation gate is
# membership (enforced in the service); this is the role→permission layer a real
# registry will later own. Security depth is out of scope (KB / social-net).
_LEADERSHIP = {"ceo", "coo", "manager", "plant_manager"}

# The activation layer / Director. `chat:system` is the CROSS-CHANNEL firehose
# read used to decide who wakes — deliberately NOT granted to any agent role
# (not even leadership), so CEO isolation (R8) holds: no agent can read across
# channels it isn't in. A system reader also cannot write or manage.
_SYSTEM = {"system", "coordinator", "director"}


def default_permissions(role: str) -> set[str]:
    r = (role or "").lower()
    if r in _SYSTEM:
        return {"chat:read", "chat:system"}
    if r in _LEADERSHIP:
        return {"chat:read", "chat:write", "chat:manage"}
    # any recognized internal actor may read, write, and open rooms
    if r:
        return {"chat:read", "chat:write", "chat:manage"}
    return {"chat:read"}
