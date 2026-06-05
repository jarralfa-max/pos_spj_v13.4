"""Event dispatcher and adapters for gradual EventBus migration."""

from __future__ import annotations

from typing import Any, Protocol

from backend.shared.events.event_bus import EventBus
from backend.shared.events.event_contracts import DomainEvent


class LegacyEventBus(Protocol):
    """Protocol for existing event buses that publish name/payload pairs."""

    def publish(self, event_name: str, payload: dict[str, Any]) -> Any:
        """Publish a legacy event without requiring typed event support."""


class EventDispatcher:
    """Dispatch typed events and optionally mirror them to a legacy bus.

    This keeps FASE 4 additive: new use cases can publish `DomainEvent` while
    existing modules continue using the current EventBus until they are migrated.
    """

    def __init__(self, event_bus: EventBus, legacy_event_bus: LegacyEventBus | None = None) -> None:
        self._event_bus = event_bus
        self._legacy_event_bus = legacy_event_bus

    def dispatch(self, event: DomainEvent) -> None:
        self._event_bus.publish(event)
        if self._legacy_event_bus is not None:
            self._legacy_event_bus.publish(event.event_name.value, event.to_dict())

    def dispatch_many(self, events: list[DomainEvent]) -> None:
        for event in events:
            self.dispatch(event)
