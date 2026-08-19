"""P0 — the store: creation, membership, append-only ordering, `since`."""
from __future__ import annotations


def test_create_channel_records_owner_and_members(store):
    ch = store.create_channel("incident", "ht", "HT-1", creator="COO-1", members=["EMP-QA-17"])
    assert store.member_role(ch["id"], "COO-1") == "owner"
    assert store.is_member(ch["id"], "EMP-QA-17")
    assert not store.is_member(ch["id"], "NOBODY")
    assert set(store.members(ch["id"])) == {"COO-1", "EMP-QA-17"}


def test_messages_are_append_only_and_ordered_by_seq(store):
    ch = store.create_channel("group", "g", None, creator="A", members=["B"])
    m1 = store.add_message(ch["id"], "A", "first", "internal", "internal", [], None)
    m2 = store.add_message(ch["id"], "B", "second", "internal", "internal", [], None)
    assert m2["seq"] > m1["seq"]
    history = store.messages_since(ch["id"], 0)
    assert [m["body"] for m in history] == ["first", "second"]


def test_since_cursor_returns_only_newer(store):
    ch = store.create_channel("group", "g", None, creator="A", members=["B"])
    m1 = store.add_message(ch["id"], "A", "first", "internal", "internal", [], None)
    store.add_message(ch["id"], "B", "second", "internal", "internal", [], None)
    newer = store.messages_since(ch["id"], m1["seq"])
    assert [m["body"] for m in newer] == ["second"]


def test_mentions_roundtrip_as_list(store):
    ch = store.create_channel("group", "g", None, creator="A", members=["B"])
    m = store.add_message(ch["id"], "A", "hi @B", "internal", "internal", ["B"], None)
    assert store.get_message(m["id"])["mentions"] == ["B"]
