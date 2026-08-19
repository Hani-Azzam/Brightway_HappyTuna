"""
Loads persona definitions from personas.yaml. Personas live in that
config file (not Python) so teammates can tweak attributes without
touching code.
"""
import os
from pathlib import Path

import yaml

_PERSONAS_PATH = Path(os.environ.get(
    "PERSONAS_CONFIG_PATH",
    Path(__file__).parent / "personas.yaml",
))

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        with open(_PERSONAS_PATH) as f:
            data = yaml.safe_load(f)
        _cache = data["personas"]
        for persona_id, persona in _cache.items():
            persona["persona_id"] = persona_id
    return _cache


def get_persona(persona_id: str) -> dict:
    personas = _load()
    if persona_id not in personas:
        raise KeyError(f"Unknown persona_id: {persona_id!r}")
    return personas[persona_id]


def all_persona_ids() -> list[str]:
    return list(_load().keys())


def all_personas() -> list[dict]:
    return list(_load().values())
