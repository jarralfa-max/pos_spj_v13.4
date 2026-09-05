"""AssetSyncConflict — offline-first conflict record (ASSET-21, §105-106).

**This is vocabulary/data-shape only.** No actual offline sync engine,
outbox consumer, or conflict-resolution UI is wired up for Activos in this
phase — nothing in `domain/assets` or `application/assets` has a live
connection to the repo's real, already-existing sync engine (`sync/`, per
CLAUDE.md's own architecture section). Building a fake local-write queue or
mock "syncing" UI without a real backend to sync against would be theater,
not progress — the same judgment call already made for ASSET-19's read-only
maintenance board and ASSET-20's honest density-gap disclosure.

What this phase DOES provide, legitimately: the entity shape and status
vocabulary (`AssetSyncStatus`, `AssetSyncConflictType`,
`AssetSyncConflictStatus`) that a future phase — once
`backend/infrastructure/db/repositories/assets/` exists and can be wired to
`sync/` — needs to represent "two writes to the same asset/assignment/work
order/disposal/physical count happened on different devices before they
could reconcile" (§106). Never auto-resolved; every resolution here is an
explicit call, keeping BOTH sides' data until a human or a defined merge
policy decides (§106: "No sobrescribir silenciosamente").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetSyncConflictStatus, AssetSyncConflictType
from backend.domain.assets.exceptions import (
    AssetDomainError,
    AssetSyncConflictAlreadyResolvedError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetSyncConflict:
    id: str
    asset_id: str
    conflict_type: AssetSyncConflictType
    local_operation_id: str
    remote_operation_id: str
    local_payload_json: str
    remote_payload_json: str
    status: AssetSyncConflictStatus = AssetSyncConflictStatus.OPEN
    resolved_by: str | None = None
    resolution_notes: str = ""
    detected_at: str = field(default_factory=_utcnow)
    resolved_at: str | None = None

    @classmethod
    def create(cls, asset_id: str, conflict_type: AssetSyncConflictType,
               local_operation_id: str, remote_operation_id: str,
               local_payload_json: str, remote_payload_json: str) -> "AssetSyncConflict":
        if not asset_id:
            raise AssetDomainError("AssetSyncConflict.asset_id is required")
        if local_operation_id == remote_operation_id:
            raise AssetDomainError(
                "AssetSyncConflict requires two distinct operation_id values "
                "(same operation_id means the same write, not a conflict)")
        return cls(
            id=new_uuid(), asset_id=asset_id, conflict_type=conflict_type,
            local_operation_id=local_operation_id, remote_operation_id=remote_operation_id,
            local_payload_json=local_payload_json, remote_payload_json=remote_payload_json,
        )

    def is_open(self) -> bool:
        return self.status is AssetSyncConflictStatus.OPEN

    def _resolve(self, status: AssetSyncConflictStatus, resolved_by: str, notes: str) -> None:
        if not self.is_open():
            raise AssetSyncConflictAlreadyResolvedError(
                f"Este conflicto ya fue resuelto ({self.status.value})")
        if not resolved_by:
            raise AssetDomainError("AssetSyncConflict resolution requires a resolver")
        self.status = status
        self.resolved_by = resolved_by
        self.resolution_notes = notes
        self.resolved_at = _utcnow()

    def keep_local(self, resolved_by: str, notes: str = "") -> None:
        self._resolve(AssetSyncConflictStatus.RESOLVED_KEEP_LOCAL, resolved_by, notes)

    def keep_remote(self, resolved_by: str, notes: str = "") -> None:
        self._resolve(AssetSyncConflictStatus.RESOLVED_KEEP_REMOTE, resolved_by, notes)

    def resolve_merged(self, resolved_by: str, notes: str = "") -> None:
        self._resolve(AssetSyncConflictStatus.RESOLVED_MERGED, resolved_by, notes)
