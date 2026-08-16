"""CustomerSyncConflictRepository (CRM-20, §92). Mirrors
backend/infrastructure/db/repositories/customers/customer_duplicate_candidate_repository.py's shape."""

from __future__ import annotations

import json

from backend.domain.customers.entities.customer_sync_conflict import CustomerSyncConflict
from backend.domain.customers.enums import CustomerSyncConflictType, SyncConflictStatus
from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase

_COLS = (
    "id, customer_id, conflict_type, local_version, remote_snapshot_json, status,"
    " detail, detected_at, resolved_at, resolved_by_user_id, resolution_note, operation_id"
)


class CustomerSyncConflictRepository(CustomerRepositoryBase):
    def save(self, conflict: CustomerSyncConflict) -> None:
        self._execute(
            f"INSERT INTO customer_sync_conflicts ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(conflict))

    def update(self, conflict: CustomerSyncConflict) -> None:
        self._execute(
            "UPDATE customer_sync_conflicts SET status=?, resolved_at=?,"
            " resolved_by_user_id=?, resolution_note=? WHERE id=?",
            (conflict.status.value, conflict.resolved_at, conflict.resolved_by_user_id,
             conflict.resolution_note, conflict.id))

    def get(self, conflict_id: str) -> CustomerSyncConflict | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_sync_conflicts WHERE id=?", (conflict_id,))
        return self._hydrate(row) if row else None

    def list_open_for_customer(self, customer_id: str) -> list[CustomerSyncConflict]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_sync_conflicts"
            " WHERE customer_id=? AND status='OPEN' ORDER BY detected_at ASC", (customer_id,))
        return [self._hydrate(r) for r in rows]

    def list_open(self, *, limit: int = 200) -> list[CustomerSyncConflict]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_sync_conflicts"
            " WHERE status='OPEN' ORDER BY detected_at ASC LIMIT ?", (limit,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(conflict: CustomerSyncConflict) -> tuple:
        return (
            conflict.id, conflict.customer_id, conflict.conflict_type.value,
            conflict.local_version, json.dumps(conflict.remote_snapshot), conflict.status.value,
            conflict.detail, conflict.detected_at, conflict.resolved_at,
            conflict.resolved_by_user_id, conflict.resolution_note, conflict.operation_id,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerSyncConflict:
        return CustomerSyncConflict(
            id=row["id"], customer_id=row["customer_id"],
            conflict_type=CustomerSyncConflictType(row["conflict_type"]),
            local_version=row["local_version"],
            remote_snapshot=json.loads(row["remote_snapshot_json"] or "{}"),
            status=SyncConflictStatus(row["status"]), detail=row["detail"] or "",
            detected_at=row["detected_at"], resolved_at=row["resolved_at"],
            resolved_by_user_id=row["resolved_by_user_id"],
            resolution_note=row["resolution_note"] or "", operation_id=row["operation_id"] or "",
        )
