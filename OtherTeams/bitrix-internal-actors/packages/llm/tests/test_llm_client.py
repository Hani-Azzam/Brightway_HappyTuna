"""Unit tests for the OpenAI-backed LlmClient — no network.

We patch the OpenAI client the LlmClient builds, so we assert on how we call the
SDK (model, temperature, seed, messages) and how we unwrap the response, without
hitting the API.
"""
from types import SimpleNamespace

import pytest

from packages.llm.llm_client import LlmClient, LlmConfig


class _FakeCompletions:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hello world"))]
        )


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())


def _client_with_fake(**cfg_overrides) -> tuple[LlmClient, _FakeOpenAI]:
    cfg = LlmConfig(api_key="sk-test", **cfg_overrides)
    client = LlmClient(cfg)
    fake = _FakeOpenAI()
    client._client = fake  # inject the fake SDK client
    return client, fake


def test_invoke_returns_message_content():
    client, _ = _client_with_fake()
    assert client.invoke([{"role": "user", "content": "hi"}]) == "hello world"


def test_invoke_forwards_model_temperature_seed_and_messages():
    client, fake = _client_with_fake(model_name="gpt-4o", temperature=0.3, seed=42)
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    client.invoke(msgs)
    sent = fake.chat.completions.last_kwargs
    assert sent["model"] == "gpt-4o"
    assert sent["temperature"] == 0.3
    assert sent["seed"] == 42
    assert sent["messages"] == msgs


def test_empty_api_key_rejected():
    with pytest.raises(ValueError):
        LlmClient(LlmConfig(api_key=""))


def test_out_of_range_temperature_rejected():
    with pytest.raises(ValueError):
        LlmClient(LlmConfig(api_key="sk-test", temperature=5.0))


def test_none_content_becomes_empty_string():
    client, fake = _client_with_fake()

    def _create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))])

    fake.chat.completions.create = _create
    assert client.invoke([{"role": "user", "content": "hi"}]) == ""
