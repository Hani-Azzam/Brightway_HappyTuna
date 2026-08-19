"""P3 — the employee agentkit adapter reaching chat over REST."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.employee.tools.internal_messaging_adapter import ReadChannel, SendChatMessage
from services.internal_messaging.transport.rest.app import create_rest_app


@pytest.fixture
def client(service):
    return TestClient(create_rest_app(service))


@pytest.fixture
def channel(client):
    return client.post(
        "/api/channels",
        headers={"Authorization": "Bearer COO-1"},
        json={"type": "incident", "members": ["EMP-QA-17"], "correlation_id": "HT-2026-001"},
    ).json()["data"]["channel"]


def test_employee_sends_and_reads_via_rest(client, channel):
    send = SendChatMessage(http=client, employee_id="EMP-QA-17")
    res = send.run(channel=channel, body="Salmonella suspected @COO-1")
    assert res.ok
    assert res.is_idempotent is False              # a write runs exactly once
    assert set(res.value["delivered_to"]) == {"COO-1", "EMP-QA-17"}

    read = ReadChannel(http=client, employee_id="EMP-QA-17")
    res = read.run(channel=channel)
    assert res.ok and res.is_idempotent is True
    assert res.value["messages"][0]["sender"] == "EMP-QA-17"


def test_identity_is_bound_not_forgeable(client, channel):
    # The adapter always posts as its bound employee_id; an OUTSIDER adapter is
    # denied because it isn't a member — the LLM can't choose the identity.
    outsider = SendChatMessage(http=client, employee_id="OUTSIDER-1")
    res = outsider.run(channel=channel, body="not allowed")
    assert res.ok is False
    assert res.error  # 403 from the service, surfaced as a tool error
