"""PostgresStore round-trip — the durable production backend.

Skipped unless a real Postgres is reachable via CHAT_TEST_DB_URL, e.g.:
    CHAT_TEST_DB_URL=postgresql://bitrix:bitrix@localhost/bitrix_chat \
      python -m pytest services/internal_messaging/tests/test_postgres_store.py

Proves the Postgres backend satisfies the same contract the service depends on
(seq monotonic from the shared sequence, mentions decoded, firehose ordering)."""
from __future__ import annotations

import os

import pytest

DSN = os.environ.get("CHAT_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="set CHAT_TEST_DB_URL to run Postgres tests")


@pytest.fixture
def pg_store():
    from services.internal_messaging.domain.store_postgres import PostgresStore
    from services.internal_messaging.integration.clock import FixedClock
    from services.internal_messaging.integration.ids import UuidFactory

    return PostgresStore(DSN, FixedClock(), UuidFactory())


def test_channel_membership_and_message_roundtrip(pg_store):
    ch = pg_store.create_channel("incident", "ht", "HT-1", "COO-1", ["EMP-QA-17"])
    cid = ch["id"]
    assert pg_store.member_role(cid, "COO-1") == "owner"
    assert pg_store.is_member(cid, "EMP-QA-17") and not pg_store.is_member(cid, "OUTSIDER")

    m1 = pg_store.add_message(cid, "EMP-QA-17", "LAB-781 POSITIVE @COO-1",
                              "internal", "internal", ["COO-1"], "HT-1")
    assert m1["mentions"] == ["COO-1"]                 # decoded from storage
    m2 = pg_store.add_message(cid, "COO-1", "ack", "internal", "internal", [], "HT-1")
    assert m2["seq"] > m1["seq"]                       # monotonic from chat_seq

    hist = pg_store.messages_since(cid, since=m1["seq"])
    assert [m["id"] for m in hist] == [m2["id"]]       # only newer
    assert pg_store.all_messages_since(0)[-1]["id"] == m2["id"]
