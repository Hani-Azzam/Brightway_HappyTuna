"""Shared event contracts published on the bus.

This module is the single source of truth for the *shape* of a MESSAGE_POSTED
event. Other teams (COO, CEO, audit) import these models to validate what they
receive, so the field names here are a cross-team contract — change them and you
break consumers.
"""

from __future__ import annotations

from pydantic import BaseModel


class MessagePostedPayload(BaseModel):
    """The 'what happened' detail of a posted message.

    Note we ship IDs and labels — never the message *body*. Consumers fetch the
    body over HTTP if they're allowed to; the event itself stays small and leaks
    no channel content onto the bus.
    """

    channelId: str
    messageId: str
    mentions: list[str]          # agent_ids the message tagged with @
    trustLabel: str              # internal | external | untrusted
    correlationId: str | None = None   # ties the event to a crisis incident


class MessagePostedEvent(BaseModel):
    """The full envelope put on the bus for every posted message."""

    eventType: str = "MESSAGE_POSTED"
    actorId: str                 # the agent who posted (the sender)
    payload: MessagePostedPayload
