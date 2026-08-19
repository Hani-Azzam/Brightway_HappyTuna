"""Routing rules in isolation (no DB, no chat)."""
from services.coordinator.events import ActivationEvent
from services.coordinator.rules import route


def _chat(mentions, sender="EMP-QA-17"):
    return ActivationEvent(
        kind="CHAT_MESSAGE", source="internal_messaging", actor_id=sender, mentions=mentions
    )


def test_chat_message_wakes_mentioned_agents():
    assert route(_chat(["COO-1"])) == ["COO-1"]


def test_sender_is_never_self_activated():
    assert route(_chat(["EMP-QA-17", "COO-1"], sender="EMP-QA-17")) == ["COO-1"]


def test_mentions_are_deduped_in_order():
    assert route(_chat(["COO-1", "COO-1", "BOARD-1"])) == ["COO-1", "BOARD-1"]


def test_scenario_event_maps_to_fixed_agents():
    ev = ActivationEvent(kind="SCENARIO_EVENT", source="scenario", name="SUSPICIOUS_SAMPLE")
    assert route(ev) == ["EMP-QA-17", "COO-1"]


def test_unknown_event_wakes_nobody():
    assert route(ActivationEvent(kind="OTHER", source="x")) == []
    assert route(ActivationEvent(kind="SCENARIO_EVENT", source="scenario", name="NOPE")) == []
