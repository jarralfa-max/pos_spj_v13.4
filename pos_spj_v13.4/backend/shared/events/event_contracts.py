"""Typed event contracts shared by desktop and future API entrypoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from backend.shared.events.event_names import EventName


EventPayload = Mapping[str, Any]


@dataclass(frozen=True)
class DomainEvent:
    """Canonical typed domain event contract.

    Every critical mutation should include `operation_id` so logs, persistence,
    handlers, tickets, and future API responses can be correlated.
    """

    event_name: EventName
    operation_id: str
    entity_id: str
    branch_id: str
    source_module: str
    payload: EventPayload = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str | None = None
    user_name: str | None = None

    def __post_init__(self) -> None:
        missing = []
        for field_name in ("operation_id", "entity_id", "branch_id", "source_module"):
            if not getattr(self, field_name):
                missing.append(field_name)
        if self.user_id is None and self.user_name is None:
            missing.append("user_id or user_name")
        if missing:
            raise ValueError("Missing required event field(s): " + ", ".join(missing))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_name": self.event_name.value,
            "operation_id": self.operation_id,
            "entity_id": self.entity_id,
            "branch_id": self.branch_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "timestamp": self.timestamp.isoformat(),
            "source_module": self.source_module,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DomainEvent":
        timestamp_value = data.get("timestamp")
        timestamp = (
            datetime.fromisoformat(str(timestamp_value))
            if timestamp_value is not None
            else datetime.now(timezone.utc)
        )
        return cls(
            event_id=str(data.get("event_id") or uuid4()),
            event_name=EventName(str(data["event_name"])),
            operation_id=str(data["operation_id"]),
            entity_id=str(data["entity_id"]),
            branch_id=str(data["branch_id"]),
            user_id=None if data.get("user_id") is None else str(data.get("user_id")),
            user_name=None if data.get("user_name") is None else str(data.get("user_name")),
            timestamp=timestamp,
            source_module=str(data["source_module"]),
            payload=dict(data.get("payload") or {}),
        )


def create_domain_event(
    *,
    event_name: EventName,
    operation_id: str,
    entity_id: str,
    branch_id: str,
    source_module: str,
    payload: EventPayload | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
) -> DomainEvent:
    return DomainEvent(
        event_name=event_name,
        operation_id=operation_id,
        entity_id=entity_id,
        branch_id=branch_id,
        user_id=user_id,
        user_name=user_name,
        source_module=source_module,
        payload=payload or {},
    )
