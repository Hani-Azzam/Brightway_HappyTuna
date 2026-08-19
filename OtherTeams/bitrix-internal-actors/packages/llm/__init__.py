"""packages.llm — concrete LLM clients.

`AnthropicClient` (Claude) is the client the simulated agents use. `LlmClient`
(OpenAI-compatible) is kept for callers that want an OpenAI/NIM endpoint. Both are
exported lazily so importing this package pulls in neither SDK until a client is
actually constructed.
"""
from __future__ import annotations

__all__ = ["AnthropicClient", "AnthropicConfig", "LlmClient", "LlmConfig"]


def __getattr__(name: str):
    if name in ("AnthropicClient", "AnthropicConfig"):
        from packages.llm import anthropic_client as _m
        return getattr(_m, name)
    if name in ("LlmClient", "LlmConfig"):
        from packages.llm import llm_client as _m
        return getattr(_m, name)
    raise AttributeError(f"module 'packages.llm' has no attribute {name!r}")
