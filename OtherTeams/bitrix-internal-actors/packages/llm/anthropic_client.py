"""LLM client backed by the Anthropic API (Claude).

Implements the same `LLM` protocol the ReAct loop expects:
`invoke(messages: list[dict]) -> str`, where each message is the OpenAI-style
chat shape `{"role": "system"|"user"|"assistant", "content": str}`.

Two shape differences from OpenAI are handled here:
  - Anthropic takes the system prompt as a **separate `system` parameter**, not a
    message with `role: "system"`. Any system messages are pulled out and joined
    into it; the remaining messages (which already start with `user` and alternate)
    are passed through as the conversation.
  - The reply is a list of content blocks; only the **text** is returned (any
    thinking/other blocks are ignored), so the caller still gets a plain string.

Defaults to `claude-opus-4-8` (the most capable model). Override the model for
cheaper/faster simulation runs via `EMPLOYEE_ANTHROPIC_MODEL=claude-haiku-4-5`.
`temperature`/`seed` are intentionally not sent — Opus 4.8 rejects them — and
`thinking` is omitted so this client works unchanged across every Claude model
(the ReAct system prompt already constrains the reply to one JSON object).
"""
from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class AnthropicConfig:
    api_key: str
    model_name: str = _DEFAULT_MODEL
    max_tokens: int = 4096
    timeout: float = 60.0


class AnthropicClient:
    def __init__(self, config: AnthropicConfig) -> None:
        if not config.api_key:
            raise ValueError("config.api_key is required and cannot be empty")
        import anthropic  # lazy: only needed when this client is actually built

        self._config = config
        self._client = anthropic.Anthropic(api_key=config.api_key, timeout=config.timeout)

    def invoke(self, messages: list[dict]) -> str:
        system = "\n\n".join(
            m["content"] for m in messages if m.get("role") == "system"
        )
        convo = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") != "system"
        ]
        kwargs: dict = {
            "model": self._config.model_name,
            "max_tokens": self._config.max_tokens,
            "messages": convo,
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        return "".join(block.text for block in response.content if block.type == "text")
