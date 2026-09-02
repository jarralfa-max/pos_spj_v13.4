"""FraudCaseRepository — persist/reconstruct `FraudCase` (LOY-26, §29)."""

from __future__ import annotations

from backend.domain.loyalty.entities.fraud_case import FraudCase
from backend.domain.loyalty.enums import FraudCaseStatus, FraudCaseSubjectType
from backend.infrastructure.db.repositories.loyalty.base import LoyaltyRepositoryBase


class FraudCaseRepository(LoyaltyRepositoryBase):
    def save(self, case: FraudCase) -> None:
        self._execute(
            """
            INSERT INTO loyalty_fraud_cases (
                id, subject_type, subject_id, customer_id, reason, opened_by_user_id, status,
                reviewed_by_user_id, resolution_notes, opened_at, resolved_at, created_at,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                reviewed_by_user_id=excluded.reviewed_by_user_id,
                resolution_notes=excluded.resolution_notes,
                resolved_at=excluded.resolved_at,
                updated_at=excluded.updated_at
            """,
            (
                case.id, case.subject_type.value, case.subject_id, case.customer_id,
                case.reason, case.opened_by_user_id, case.status.value,
                case.reviewed_by_user_id, case.resolution_notes, case.opened_at,
                case.resolved_at, case.created_at, case.updated_at,
            ),
        )

    def get(self, case_id: str) -> FraudCase | None:
        row = self._query_one("SELECT * FROM loyalty_fraud_cases WHERE id=?", (case_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[FraudCase]:
        rows = self._query(
            "SELECT * FROM loyalty_fraud_cases WHERE customer_id=? ORDER BY opened_at DESC",
            (customer_id,))
        return [self._hydrate(row) for row in rows]

    def list_open(self) -> list[FraudCase]:
        rows = self._query(
            "SELECT * FROM loyalty_fraud_cases WHERE status IN ('OPEN','UNDER_REVIEW')"
            " ORDER BY opened_at")
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> FraudCase:
        return FraudCase(
            id=row["id"], subject_type=FraudCaseSubjectType(row["subject_type"]),
            subject_id=row["subject_id"], customer_id=row["customer_id"], reason=row["reason"],
            opened_by_user_id=row["opened_by_user_id"], status=FraudCaseStatus(row["status"]),
            reviewed_by_user_id=row["reviewed_by_user_id"],
            resolution_notes=row["resolution_notes"], opened_at=row["opened_at"],
            resolved_at=row["resolved_at"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
