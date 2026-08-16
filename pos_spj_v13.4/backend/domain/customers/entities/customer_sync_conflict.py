"""CustomerSyncConflict (§92, CRM-20) — records a detected divergence
between a local (possibly offline) mutation and the customer's current
persisted state, instead of silently overwriting one with the other.

Detection uses optimistic concurrency on ``Customer.version`` (already
built, CRM-3) rather than inventing a new Lamport-clock/timestamp scheme:
an incoming mutation carries the version it believed it was editing; if
that no longer matches the customer's current version, someone else's
change landed first — a conflict, not a normal update.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customers.enums import CustomerSyncConflictType, SyncConflictStatus
from backend.domain.customers.exceptions import CustomerSyncConflictAlreadyResolvedError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerSyncConflict:
    id: str
    customer_id: str
    conflict_type: CustomerSyncConflictType
    local_version: int
    remote_snapshot: dict
    status: SyncConflictStatus = SyncConflictStatus.OPEN
    detail: str = ""
    detected_at: str = field(default_factory=_utcnow)
    resolved_at: str | None = None
    resolved_by_user_id: str | None = None
    resolution_note: str = ""
    operation_id: str = ""

    @classmethod
    def detect(
        cls, customer_id: str, conflict_type: CustomerSyncConflictType, local_version: int,
        remote_snapshot: dict, *, detail: str = "", operation_id: str = "",
    ) -> "CustomerSyncConflict":
        return cls(id=new_uuid(), customer_id=customer_id, conflict_type=conflict_type,
                   local_version=local_version, remote_snapshot=dict(remote_snapshot),
                   detail=detail, operation_id=operation_id)

    def resolve(self, outcome: SyncConflictStatus, *, resolved_by_user_id: str,
               resolution_note: str = "") -> None:
        if self.status != SyncConflictStatus.OPEN:
            raise CustomerSyncConflictAlreadyResolvedError(
                f"El conflicto {self.id} ya fue resuelto ({self.status.value})")
        if outcome == SyncConflictStatus.OPEN:
            raise CustomerSyncConflictAlreadyResolvedError(
                "La resolución debe ser RESOLVED_LOCAL, RESOLVED_REMOTE o RESOLVED_MERGED")
        self.status = outcome
        self.resolved_by_user_id = resolved_by_user_id
        self.resolution_note = resolution_note
        self.resolved_at = _utcnow()
