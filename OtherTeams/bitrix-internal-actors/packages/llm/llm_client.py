"""LLM client backed by the OpenAI API.

Backend = OpenAI for now. Because the OpenAI SDK also speaks to any
OpenAI-compatible endpoint, switching to NVIDIA NIM later is a pure config
change: set `base_url` to the NIM URL and pick a NIM `model_name`. No code change,
and nothing in `agentkit` is touched (it depends only on the `LLM` protocol).

Interface: `invoke(messages: list[dict]) -> str`, where each message is the
OpenAI chat shape {"role": "system"|"user"|"assistant", "content": str}.
"""
from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI


@dataclass
class LlmConfig:
    api_key: str
    model_name: str = "gpt-4o-mini"   # dev default; use gpt-4o for the "real" runs
    base_url: str | None = None       # None -> OpenAI default; set to a NIM URL to switch later
    temperature: float = 0.1
    timeout: float = 30.0
    seed: int | None = None           # near-deterministic sampling for reproducible runs


class LlmClient:
    def __init__(self, config: LlmConfig) -> None:
        if not config.api_key:
            raise ValueError("config.api_key is required and cannot be empty")
        if not (0.0 <= config.temperature <= 2.0):
            raise ValueError("config.temperature must be between 0.0 and 2.0")
        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,   # None is valid → OpenAI's default endpoint
            timeout=config.timeout,
        )

    def invoke(self, messages: list[dict]) -> str:
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            temperature=self._config.temperature,
            seed=self._config.seed,
            messages=messages,
        )
        return response.choices[0].message.content or ""
