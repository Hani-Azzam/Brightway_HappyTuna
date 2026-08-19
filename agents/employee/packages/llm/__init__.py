"""packages.llm — the LLM client the simulated agents use.

`AnthropicClient` (Claude) is exported lazily so importing this package pulls in
no SDK until a client is actually constructed.
"""
from __future__ import annotations

__all__ = ["AnthropicClient", "AnthropicConfig"]


def __getattr__(name: str):
    if name in ("AnthropicClient", "AnthropicConfig"):
        from packages.llm import anthropic_client as _m
        return getattr(_m, name)
    raise AttributeError(f"module 'packages.llm' has no attribute {name!r}")
