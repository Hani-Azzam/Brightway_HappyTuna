"""MCP Gateway for the HappyTuna CEO agent.

    registry.py    mcp_servers.yaml -> validated ServerConfig models
    connection.py  one live MCP session per server, in one AsyncExitStack
    catalog.py     live sessions -> namespaced ToolEntry catalog with access tags
    policy.py      roles.yaml -> the subset of the catalog one role may use
    router.py      the agent-facing surface: tool lists and guarded dispatch

Import `Router` and nothing else. Reaching past it to a session, the catalog, or
the policy skips the enforcement that is the whole point of this package.
"""

from .catalog import TOOL_ACCESS, Catalog, CatalogError, build_catalog, qualify
from .connection import GatewayConnections, call_tool, describe_exception
from .models import (
    AccessLevel,
    LoginSpec,
    PolicyDecision,
    Profile,
    RoleConfig,
    ServerConfig,
    ServerStatus,
    SetupStep,
    ToolEntry,
    ToolResult,
)
from .policy import Policy, PolicyError, build_policy, get_role, load_roles
from .registry import RegistryError, load_registry
from .router import AuditLog, Router, prepare_schema, to_langchain_name

__all__ = [
    "TOOL_ACCESS",
    "AccessLevel",
    "AuditLog",
    "Catalog",
    "CatalogError",
    "Router",
    "GatewayConnections",
    "LoginSpec",
    "Policy",
    "PolicyDecision",
    "PolicyError",
    "Profile",
    "RegistryError",
    "RoleConfig",
    "ServerConfig",
    "ServerStatus",
    "SetupStep",
    "ToolEntry",
    "ToolResult",
    "build_catalog",
    "build_policy",
    "call_tool",
    "describe_exception",
    "get_role",
    "load_registry",
    "load_roles",
    "prepare_schema",
    "qualify",
    "to_langchain_name",
]
