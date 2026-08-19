from typing import Any, Callable


class Event:
    """A tiny pub/sub broker.

    Listeners register against a tag (a topic name) and only get called when
    that tag is emitted. Nothing fancy: calls are synchronous and happen on the
    caller's thread.
    """

    def __init__(self):
        # tag -> listeners, in registration order so callbacks fire predictably
        self._subscribers: dict[str, list[Callable[..., Any]]] = {}

    def subscribe(self, listener, tag: str):
        """Registers a callback function to the event."""
        # First listener for this tag creates the list; duplicates are ignored
        # so subscribing twice doesn't fire the same callback twice.
        listeners = self._subscribers.setdefault(tag, [])
        if listener not in listeners:
            listeners.append(listener)

    def unsubscribe(self, listener):
        """Removes a registered callback from the event."""
        # The listener may sit under several tags, so sweep them all and drop
        # any tag left with no listeners to keep the dict from growing stale.
        for tag in list(self._subscribers):
            listeners = self._subscribers[tag]
            if listener in listeners:
                listeners.remove(listener)
            if not listeners:
                del self._subscribers[tag]

    def emit(self, tag: str, *args, **kwargs):
        """Triggers the event and executes all subscriber callbacks."""
        if tag in self._subscribers:
            # Iterate a copy: a listener is free to unsubscribe while handling.
            for listener in list(self._subscribers[tag]):
                listener(*args, **kwargs)
