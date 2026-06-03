"""Typed events package for the SPJ refactor."""

from backend.shared.events.event_bus import EventBus, EventHandler, InMemoryEventBus
from backend.shared.events.event_contracts import DomainEvent, EventPayload, create_domain_event
from backend.shared.events.event_dispatcher import EventDispatcher, LegacyEventBus
from backend.shared.events.event_names import CRITICAL_EVENT_NAMES, EventName

__all__ = [
    "CRITICAL_EVENT_NAMES",
    "DomainEvent",
    "EventBus",
    "EventDispatcher",
    "EventHandler",
    "EventName",
    "EventPayload",
    "InMemoryEventBus",
    "LegacyEventBus",
    "create_domain_event",
]
