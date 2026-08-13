"""CustomerImportBatchRepository — persists import batch summaries. Mirrors
customer_duplicate_candidate_repository.py.
"""

from __future__ import annotations

from backend.domain.customers.entities.customer_import_batch import CustomerImportBatch
from backend.domain.customers.enums import ImportBatchStatus
from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase

_COLS = (
    "id, submitted_by_user_id, is_sensitive, total_rows, created_count, updated_count,"
    " rejected_count, duplicate_count, error_count, status, approved_by_user_id,"
    " approved_at, operation_id, created_at, updated_at"
)


class CustomerImportBatchRepository(CustomerRepositoryBase):
    def save(self, batch: CustomerImportBatch, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_import_batches ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(batch, operation_id or batch.operation_id))

    def update(self, batch: CustomerImportBatch) -> None:
        self._execute(
            "UPDATE customer_import_batches SET created_count=?, updated_count=?,"
            " rejected_count=?, duplicate_count=?, error_count=?, status=?,"
            " approved_by_user_id=?, approved_at=?, updated_at=? WHERE id=?",
            (batch.created_count, batch.updated_count, batch.rejected_count,
             batch.duplicate_count, batch.error_count, batch.status.value,
             batch.approved_by_user_id, batch.approved_at, batch.updated_at, batch.id))

    def get(self, batch_id: str) -> CustomerImportBatch | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_import_batches WHERE id=?",
                              (batch_id,))
        return self._hydrate(row) if row else None

    def list_pending_approval(self) -> list[CustomerImportBatch]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_import_batches"
            " WHERE status='PENDING_APPROVAL' ORDER BY created_at")
        return [self._hydrate(r) for r in rows]

    def save_pending_rows(self, batch_id: str, rows_json: str) -> None:
        """Round-trips a sensitive batch's submitted rows until a second
        approver processes them — see CustomerImportBatch's docstring for
        why this lives at the repository layer, not on the entity."""
        self._execute(
            "UPDATE customer_import_batches SET pending_rows_json=? WHERE id=?",
            (rows_json, batch_id))

    def get_pending_rows(self, batch_id: str) -> str | None:
        return self._scalar(
            "SELECT pending_rows_json FROM customer_import_batches WHERE id=?", (batch_id,))

    def clear_pending_rows(self, batch_id: str) -> None:
        self._execute(
            "UPDATE customer_import_batches SET pending_rows_json=NULL WHERE id=?", (batch_id,))

    @staticmethod
    def _params(batch: CustomerImportBatch, operation_id: str | None) -> tuple:
        return (
            batch.id, batch.submitted_by_user_id, int(batch.is_sensitive), batch.total_rows,
            batch.created_count, batch.updated_count, batch.rejected_count,
            batch.duplicate_count, batch.error_count, batch.status.value,
            batch.approved_by_user_id, batch.approved_at, operation_id, batch.created_at,
            batch.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerImportBatch:
        return CustomerImportBatch(
            id=row["id"], submitted_by_user_id=row["submitted_by_user_id"],
            is_sensitive=bool(row["is_sensitive"]), total_rows=row["total_rows"],
            created_count=row["created_count"], updated_count=row["updated_count"],
            rejected_count=row["rejected_count"], duplicate_count=row["duplicate_count"],
            error_count=row["error_count"], status=ImportBatchStatus(row["status"]),
            approved_by_user_id=row["approved_by_user_id"], approved_at=row["approved_at"],
            operation_id=row["operation_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
