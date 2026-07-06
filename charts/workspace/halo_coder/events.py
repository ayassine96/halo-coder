"""In-process event bus for loose coupling between modules.

Provides a protocol-compliant :class:`EventBroker` that fans typed
:class:`DomainEvent` objects to registered subscribers via bounded
queues. Follows the existing EventBroker pattern from server.py
but with dependency injection instead of class-level state.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Optional

from halo_coder.protocols import DomainEvent, EventBus


class EventBroker(EventBus):
    """Thread-safe in-process pub/sub event bus.

    Each subscriber gets a bounded queue. If a consumer falls behind
    we drop its oldest event rather than block the publisher — the
    system is designed for lossy-tolerant use cases (SSE) where clients
    reconcile state on reconnect.

    Usage::

        broker = EventBroker()
        q = broker.subscribe()
        broker.publish("spec.status", {"spec_id": "s1", "status": "ready"})
        event = q.get_nowait()
        broker.unsubscribe(q)
    """

    def __init__(self, *, queue_max: int = 200) -> None:
        """Initialize the event broker.

        Args:
            queue_max: Maximum events per subscriber before dropping oldest.
        """
        self._queue_max = queue_max
        self._subscribers: set[queue.Queue[DomainEvent]] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[DomainEvent]:
        """Register a new subscriber and return its event queue."""
        q: queue.Queue[DomainEvent] = queue.Queue(maxsize=self._queue_max)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[DomainEvent]) -> None:
        """Remove a subscriber queue."""
        with self._lock:
            self._subscribers.discard(q)

    def subscriber_count(self) -> int:
        """Return the current number of active subscribers."""
        with self._lock:
            return len(self._subscribers)

    def publish(
        self,
        event_type: str,
        data: Optional[dict[str, Any]] = None,
    ) -> DomainEvent:
        """Fan an event out to every subscriber. Never raises, never blocks.

        Args:
            event_type: A namespaced event type (e.g. ``task.status``).
            data: Optional payload dictionary.

        Returns:
            The published :class:`DomainEvent`.
        """
        event = DomainEvent(
            type=event_type,
            data=data or {},
            ts=time.time(),
        )
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (queue.Empty, queue.Full):
                    pass
        return event


def create_event_bus(*, queue_max: int = 200) -> EventBus:
    """Factory for the default event bus implementation.

    Args:
        queue_max: Maximum events per subscriber before dropping oldest.

    Returns:
        An :class:`EventBus` instance.
    """
    return EventBroker(queue_max=queue_max)


__all__ = ["EventBroker", "create_event_bus"]
