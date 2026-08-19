"""Loads mcp_servers.yaml into validated `ServerConfig` models.

Owns two things nothing else may know about: where the registry file lives, and
how a profile ("docker" / "local") becomes a concrete URL. Downstream receives a
`ServerConfig` whose `url` is already resolved, so no other layer ever branches
on environment.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import LoginSpec, Profile, ServerConfig, SetupStep

logger = logging.getLogger(__name__)

#: Selects which URL set to read out of each server's `urls` map.
PROFILE_ENV_VAR = "GATEWAY_URL_PROFILE"

#: Points at an alternative registry file. Handy for tests; not needed normally.
REGISTRY_PATH_ENV_VAR = "GATEWAY_REGISTRY_PATH"

#: Used when neither the caller nor the env var nor the file specifies one.
FALLBACK_PROFILE: Profile = "docker"

#: ceo_agent/mcp_servers.yaml -- one level up from this package.
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "mcp_servers.yaml"


class RegistryError(RuntimeError):
    """The registry file is missing, malformed, or internally inconsistent.

    Raised, not warned: a bad registry is a developer error that would otherwise
    surface much later as a confusing connection failure. An unreachable *server*
    is different -- that is a runtime condition the gateway must survive.
    """


class _ServerFile(BaseModel):
    """One `servers:` entry exactly as it appears on disk, before URL resolution."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    urls: dict[str, str] = Field(min_length=1)
    enabled: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0)
    login: LoginSpec | None = None
    post_login_setup: list[SetupStep] = Field(default_factory=list)


class _RegistryFile(BaseModel):
    """The whole registry file."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    default_profile: str = FALLBACK_PROFILE
    servers: list[_ServerFile] = Field(min_length=1)


def resolve_profile(explicit: str | None = None) -> str:
    """Decides which URL profile to use.

    Precedence: explicit argument, then `GATEWAY_URL_PROFILE`, then the file's
    `default_profile` (applied by the caller via `load_registry`), then "docker".
    """
    if explicit:
        return explicit
    from_env = os.environ.get(PROFILE_ENV_VAR, "").strip()
    return from_env or ""


def _resolve_registry_path(path: Path | str | None) -> Path:
    if path is not None:
        return Path(path)
    from_env = os.environ.get(REGISTRY_PATH_ENV_VAR, "").strip()
    return Path(from_env) if from_env else DEFAULT_REGISTRY_PATH


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RegistryError(f"Registry file not found: {path}") from exc
    except OSError as exc:
        raise RegistryError(f"Could not read registry file {path}: {exc}") from exc

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RegistryError(f"Registry file {path} is not valid YAML: {exc}") from exc

    if not isinstance(parsed, dict):
        raise RegistryError(
            f"Registry file {path} must contain a YAML mapping at the top level, "
            f"got {type(parsed).__name__}."
        )
    return parsed


def load_registry(
    path: Path | str | None = None,
    profile: str | None = None,
) -> list[ServerConfig]:
    """Reads the registry file and returns one resolved `ServerConfig` per server.

    Disabled servers are still returned: skipping them is `connection.py`'s job,
    and it must log a WARNING naming each one, which it cannot do for entries
    dropped silently here.

    Raises `RegistryError` if the file is missing or malformed, if two servers
    share an id, or if any lacks a URL for the active profile.
    """
    registry_path = _resolve_registry_path(path)
    parsed = _read_yaml(registry_path)

    try:
        registry_file = _RegistryFile.model_validate(parsed)
    except ValidationError as exc:
        raise RegistryError(f"Registry file {registry_path} is invalid:\n{exc}") from exc

    active_profile = resolve_profile(profile) or registry_file.default_profile

    seen_ids: set[str] = set()
    configs: list[ServerConfig] = []

    for entry in registry_file.servers:
        if entry.id in seen_ids:
            raise RegistryError(
                f"Duplicate server id {entry.id!r} in {registry_path}. Ids become "
                f"catalog namespaces and must be unique."
            )
        seen_ids.add(entry.id)

        url = entry.urls.get(active_profile)
        if not url:
            available = ", ".join(sorted(entry.urls)) or "none"
            raise RegistryError(
                f"Server {entry.id!r} in {registry_path} has no URL for profile "
                f"{active_profile!r}. Available profiles for this server: {available}. "
                f"Set {PROFILE_ENV_VAR} to one of those, or add the missing entry."
            )

        configs.append(
            ServerConfig(
                id=entry.id,
                url=url,
                enabled=entry.enabled,
                timeout_seconds=entry.timeout_seconds,
                login=entry.login,
                post_login_setup=entry.post_login_setup,
            )
        )

    logger.info(
        "Loaded %d server(s) from %s using profile %r: %s",
        len(configs),
        registry_path,
        active_profile,
        ", ".join(c.id for c in configs),
    )
    return configs
