"""Canonical audit helpers for HR application use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class HRAuditRecord:
    """Structured audit evidence emitted by HR use cases after persistence."""

    action: str
    operation_id: str
    entity_id: str
    actor_user_id: str | None
    branch_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, Any] = field(default_factory=dict)


class HRAuditSink(Protocol):
    """Port implemented by the canonical audit infrastructure."""

    def record(self, audit_record: HRAuditRecord) -> None:
        """Persist or forward an HR audit record."""


def record_hr_audit(
    audit_sink: HRAuditSink | None,
    *,
    action: str,
    operation_id: str,
    entity_id: str,
    actor_user_id: str | None,
    branch_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> HRAuditRecord:
    """Build and emit an audit record when a sink is configured."""

    audit_record = HRAuditRecord(
        action=action,
        operation_id=operation_id,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        branch_id=branch_id,
        metadata=metadata or {},
    )
    if audit_sink is not None:
        audit_sink.record(audit_record)
    return audit_record
