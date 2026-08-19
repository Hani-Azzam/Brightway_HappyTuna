"""KafkaPublisher: one keyed event per message on the chat.message_posted topic.

Uses a fake producer so no broker is needed; the real `confluent_kafka.Producer`
is imported lazily only when a producer is actually created."""
from __future__ import annotations

import json

from services.internal_messaging.integration.events import ChatMessagePosted, KafkaPublisher


class FakeProducer:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    def produce(self, topic, key, value):
        self.sent.append((topic, key, value))

    def poll(self, _timeout):
        pass

    def flush(self, _timeout):
        pass


def test_kafka_publisher_produces_channel_keyed_event():
    kp = KafkaPublisher("kafka:9092", "chat.message_posted")
    kp._producer = FakeProducer()          # inject fake, bypass lazy real producer

    kp.publish(ChatMessagePosted(
        event_type="chat.message_posted", actor_id="EMP-QA-17", sim_time="DAY_1",
        seq=7, channel="chan_1", message_id="msg_7", mentions=["COO-1"],
        trust_label="internal", correlation_id="HT-1", recipients=["COO-1", "EMP-QA-17"],
    ))

    (topic, key, value), = kp._producer.sent
    assert topic == "chat.message_posted"
    assert key == b"chan_1"                 # per-channel key -> per-channel ordering
    payload = json.loads(value)
    assert payload["message_id"] == "msg_7"
    assert payload["recipients"] == ["COO-1", "EMP-QA-17"]   # consumers filter by this
    assert payload["seq"] == 7                                # cursor for replay
