"""CRMSyncConflict (§92, CRM-20) — mirrors
backend/domain/customers/entities/customer_sync_conflict.py. Detection uses
optimistic concurrency on the target entity's ``updated_at`` (Lead/
Opportunity/CRMTask have no ``version`` counter like Customer does — adding
one repo-wide is out of this phase's scope; ``updated_at`` is already bumped
on every mutation across this package, same reasoning
Customer.version-based detection uses, just a coarser (second-precision)
clock instead of a counter).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import CRMSyncConflictType, SyncConflictStatus
from backend.domain.crm.exceptions import CRMSyncConflictAlreadyResolvedError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CRMSyncConflict:
    id: str
    related_entity_type: str
    related_entity_id: str
    conflict_type: CRMSyncConflictType
    local_updated_at: str
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
        cls, related_entity_type: str, related_entity_id: str,
        conflict_type: CRMSyncConflictType, local_updated_at: str, remote_snapshot: dict,
        *, detail: str = "", operation_id: str = "",
    ) -> "CRMSyncConflict":
        return cls(id=new_uuid(), related_entity_type=related_entity_type,
                   related_entity_id=related_entity_id, conflict_type=conflict_type,
                   local_updated_at=local_updated_at, remote_snapshot=dict(remote_snapshot),
                   detail=detail, operation_id=operation_id)

    def resolve(self, outcome: SyncConflictStatus, *, resolved_by_user_id: str,
               resolution_note: str = "") -> None:
        if self.status != SyncConflictStatus.OPEN:
            raise CRMSyncConflictAlreadyResolvedError(
                f"El conflicto {self.id} ya fue resuelto ({self.status.value})")
        if outcome == SyncConflictStatus.OPEN:
            raise CRMSyncConflictAlreadyResolvedError(
                "La resolución debe ser RESOLVED_LOCAL, RESOLVED_REMOTE o RESOLVED_MERGED")
        self.status = outcome
        self.resolved_by_user_id = resolved_by_user_id
        self.resolution_note = resolution_note
        self.resolved_at = _utcnow()
