"""P3 — the REST door: envelope, authz, non-member/missing-token."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.internal_messaging.transport.rest.app import create_rest_app


@pytest.fixture
def client(service):
    return TestClient(create_rest_app(service))


def _auth(agent_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {agent_id}"}


def test_full_flow_create_post_read(client):
    r = client.post(
        "/api/channels",
        headers=_auth("COO-1"),
        json={"type": "incident", "members": ["EMP-QA-17"], "correlation_id": "HT-2026-001"},
    )
    assert r.status_code == 200 and r.json()["success"]
    channel = r.json()["data"]["channel"]

    r = client.post(
        f"/api/channels/{channel}/messages",
        headers=_auth("EMP-QA-17"),
        json={"body": "Line 4 halted @COO-1"},
    )
    assert r.status_code == 200
    assert set(r.json()["data"]["delivered_to"]) == {"COO-1", "EMP-QA-17"}

    r = client.get(f"/api/channels/{channel}/messages", headers=_auth("COO-1"))
    assert r.status_code == 200
    assert r.json()["data"]["messages"][0]["body"] == "Line 4 halted @COO-1"


def test_non_member_post_is_403(client):
    channel = client.post(
        "/api/channels", headers=_auth("COO-1"), json={"type": "group", "members": ["EMP-QA-17"]}
    ).json()["data"]["channel"]
    r = client.post(
        f"/api/channels/{channel}/messages", headers=_auth("OUTSIDER-1"), json={"body": "hi"}
    )
    assert r.status_code == 403
    assert r.json()["success"] is False


def test_missing_token_is_rejected(client):
    r = client.post("/api/channels", json={"type": "group", "members": []})
    assert r.status_code == 403
