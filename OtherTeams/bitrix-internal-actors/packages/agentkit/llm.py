"""The LLM interface agentkit depends on — a structural Protocol, not a class.

`ToolAgent` only needs to send a list of chat messages and get back a string.
Keeping this a Protocol means:
  - agentkit has NO provider dependency (no openai, no langchain);
  - the concrete client lives in `packages/llm` (OpenAI today, NIM later);
  - tests inject a trivial fake with a single `invoke` method.

Message format is the OpenAI chat shape: {"role": "system"|"user"|"assistant",
"content": "..."}.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    def invoke(self, messages: list[dict]) -> str: ...
