"""In-memory typed EventBus for new code during gradual transition."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import DefaultDict, Protocol

from backend.shared.events.event_contracts import DomainEvent
from backend.shared.events.event_names import EventName


EventHandler = Callable[[DomainEvent], None]


class EventBus(Protocol):
    def subscribe(self, event_name: EventName, handler: EventHandler) -> None:
        """Subscribe a handler to one event name."""

    def publish(self, event: DomainEvent) -> None:
        """Publish one typed domain event."""


class InMemoryEventBus:
    """Minimal synchronous event bus for tests and new application services."""

    def __init__(self) -> None:
        self._handlers: DefaultDict[EventName, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: EventName, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in list(self._handlers[event.event_name]):
            handler(event)
