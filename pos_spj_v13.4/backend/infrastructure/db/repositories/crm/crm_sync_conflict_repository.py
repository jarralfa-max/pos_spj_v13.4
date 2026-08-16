"""CRMSyncConflictRepository (CRM-20, §92). Mirrors
backend/infrastructure/db/repositories/customers/customer_sync_conflict_repository.py."""

from __future__ import annotations

import json

from backend.domain.crm.entities.crm_sync_conflict import CRMSyncConflict
from backend.domain.crm.enums import CRMSyncConflictType, SyncConflictStatus
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = (
    "id, related_entity_type, related_entity_id, conflict_type, local_updated_at,"
    " remote_snapshot_json, status, detail, detected_at, resolved_at,"
    " resolved_by_user_id, resolution_note, operation_id"
)


class CRMSyncConflictRepository(CRMRepositoryBase):
    def save(self, conflict: CRMSyncConflict) -> None:
        self._execute(
            f"INSERT INTO crm_sync_conflicts ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(conflict))

    def update(self, conflict: CRMSyncConflict) -> None:
        self._execute(
            "UPDATE crm_sync_conflicts SET status=?, resolved_at=?,"
            " resolved_by_user_id=?, resolution_note=? WHERE id=?",
            (conflict.status.value, conflict.resolved_at, conflict.resolved_by_user_id,
             conflict.resolution_note, conflict.id))

    def get(self, conflict_id: str) -> CRMSyncConflict | None:
        row = self._query_one(f"SELECT {_COLS} FROM crm_sync_conflicts WHERE id=?", (conflict_id,))
        return self._hydrate(row) if row else None

    def list_open_for_entity(self, related_entity_type: str,
                             related_entity_id: str) -> list[CRMSyncConflict]:
        rows = self._query(
            f"SELECT {_COLS} FROM crm_sync_conflicts WHERE related_entity_type=?"
            " AND related_entity_id=? AND status='OPEN' ORDER BY detected_at ASC",
            (related_entity_type, related_entity_id))
        return [self._hydrate(r) for r in rows]

    def list_open(self, *, limit: int = 200) -> list[CRMSyncConflict]:
        rows = self._query(
            f"SELECT {_COLS} FROM crm_sync_conflicts"
            " WHERE status='OPEN' ORDER BY detected_at ASC LIMIT ?", (limit,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(conflict: CRMSyncConflict) -> tuple:
        return (
            conflict.id, conflict.related_entity_type, conflict.related_entity_id,
            conflict.conflict_type.value, conflict.local_updated_at,
            json.dumps(conflict.remote_snapshot), conflict.status.value, conflict.detail,
            conflict.detected_at, conflict.resolved_at, conflict.resolved_by_user_id,
            conflict.resolution_note, conflict.operation_id,
        )

    @staticmethod
    def _hydrate(row: dict) -> CRMSyncConflict:
        return CRMSyncConflict(
            id=row["id"], related_entity_type=row["related_entity_type"],
            related_entity_id=row["related_entity_id"],
            conflict_type=CRMSyncConflictType(row["conflict_type"]),
            local_updated_at=row["local_updated_at"],
            remote_snapshot=json.loads(row["remote_snapshot_json"] or "{}"),
            status=SyncConflictStatus(row["status"]), detail=row["detail"] or "",
            detected_at=row["detected_at"], resolved_at=row["resolved_at"],
            resolved_by_user_id=row["resolved_by_user_id"],
            resolution_note=row["resolution_note"] or "", operation_id=row["operation_id"] or "",
        )
