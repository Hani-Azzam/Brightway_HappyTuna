"""AnthropicClient maps the OpenAI-style message list onto the Anthropic API:
system messages become the `system` param, the rest pass through as `messages`,
and only text blocks are returned. A fake client avoids any network call."""
from __future__ import annotations

import pytest

from packages.llm.anthropic_client import AnthropicClient, AnthropicConfig


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Resp('{"action":"final_answer","answer":"ok"}')


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def _client(**cfg) -> AnthropicClient:
    c = AnthropicClient(AnthropicConfig(api_key="x", **cfg))
    c._client = _FakeClient()          # bypass the real SDK client (no network)
    return c


def test_system_is_pulled_out_and_text_returned():
    c = _client(model_name="claude-opus-4-8", max_tokens=1024)
    out = c.invoke([
        {"role": "system", "content": "You are Dana."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "{}"},
        {"role": "user", "content": "go"},
    ])
    assert out == '{"action":"final_answer","answer":"ok"}'

    call = c._client.messages.calls[0]
    assert call["system"] == "You are Dana."
    assert call["model"] == "claude-opus-4-8"
    assert call["max_tokens"] == 1024
    # No 'system' role leaks into messages; the conversation is preserved in order.
    assert [m["role"] for m in call["messages"]] == ["user", "assistant", "user"]


def test_multiple_system_messages_are_joined():
    c = _client()
    c.invoke([
        {"role": "system", "content": "A"},
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "B"},
    ])
    assert c._client.messages.calls[0]["system"] == "A\n\nB"


def test_no_system_key_when_absent():
    c = _client()
    c.invoke([{"role": "user", "content": "hi"}])
    assert "system" not in c._client.messages.calls[0]


def test_empty_api_key_raises():
    with pytest.raises(ValueError):
        AnthropicClient(AnthropicConfig(api_key=""))
