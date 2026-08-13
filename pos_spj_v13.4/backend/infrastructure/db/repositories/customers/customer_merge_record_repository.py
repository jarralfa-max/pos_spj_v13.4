"""CustomerMergeRecordRepository — persists proposed/executed/rejected
merges. Mirrors customer_duplicate_candidate_repository.py.
"""

from __future__ import annotations

from backend.domain.customers.entities.customer_merge_record import CustomerMergeRecord
from backend.domain.customers.enums import CustomerMergeStatus
from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase

_COLS = (
    "id, master_customer_id, merged_customer_id, duplicate_candidate_id,"
    " proposed_by_user_id, reason, status, executed_by_user_id, executed_at,"
    " rejected_by_user_id, rejected_at, rejection_reason, operation_id,"
    " created_at, updated_at"
)


class CustomerMergeRecordRepository(CustomerRepositoryBase):
    def save(self, record: CustomerMergeRecord, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_merge_records ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(record, operation_id or record.operation_id))

    def update(self, record: CustomerMergeRecord) -> None:
        self._execute(
            "UPDATE customer_merge_records SET status=?, executed_by_user_id=?, executed_at=?,"
            " rejected_by_user_id=?, rejected_at=?, rejection_reason=?, updated_at=?"
            " WHERE id=?",
            (record.status.value, record.executed_by_user_id, record.executed_at,
             record.rejected_by_user_id, record.rejected_at, record.rejection_reason,
             record.updated_at, record.id))

    def get(self, record_id: str) -> CustomerMergeRecord | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_merge_records WHERE id=?",
                              (record_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[CustomerMergeRecord]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_merge_records"
            " WHERE master_customer_id=? OR merged_customer_id=? ORDER BY created_at DESC",
            (customer_id, customer_id))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(record: CustomerMergeRecord, operation_id: str | None) -> tuple:
        return (
            record.id, record.master_customer_id, record.merged_customer_id,
            record.duplicate_candidate_id, record.proposed_by_user_id, record.reason,
            record.status.value, record.executed_by_user_id, record.executed_at,
            record.rejected_by_user_id, record.rejected_at, record.rejection_reason,
            operation_id, record.created_at, record.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerMergeRecord:
        return CustomerMergeRecord(
            id=row["id"], master_customer_id=row["master_customer_id"],
            merged_customer_id=row["merged_customer_id"],
            duplicate_candidate_id=row["duplicate_candidate_id"],
            proposed_by_user_id=row["proposed_by_user_id"], reason=row["reason"] or "",
            status=CustomerMergeStatus(row["status"]),
            executed_by_user_id=row["executed_by_user_id"], executed_at=row["executed_at"],
            rejected_by_user_id=row["rejected_by_user_id"], rejected_at=row["rejected_at"],
            rejection_reason=row["rejection_reason"] or "", operation_id=row["operation_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
