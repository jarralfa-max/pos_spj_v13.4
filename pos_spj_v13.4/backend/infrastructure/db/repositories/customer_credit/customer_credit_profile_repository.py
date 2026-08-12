"""CustomerCreditProfileRepository — persists the CustomerCreditProfile
aggregate. Mirrors
backend/infrastructure/db/repositories/customer_service/service_case_repository.py.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.customer_credit.entities.customer_credit_profile import CustomerCreditProfile
from backend.domain.customer_credit.enums import CreditProfileStatus, CreditRiskLevel
from backend.infrastructure.db.repositories.customer_credit.base import (
    CustomerCreditRepositoryBase,
)

_PROFILE_COLS = (
    "id, customer_id, status, credit_limit, payment_terms_days, risk_level,"
    " requested_by_user_id, authorized_at, authorized_by_user_id, suspended_at,"
    " blocked_at, review_at, closed_at, close_reason, version, operation_id,"
    " created_at, updated_at"
)


class CustomerCreditProfileRepository(CustomerCreditRepositoryBase):
    def save(self, profile: CustomerCreditProfile, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_credit_profiles ({_PROFILE_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(profile, operation_id or profile.operation_id))

    def update(self, profile: CustomerCreditProfile) -> None:
        self._execute(
            "UPDATE customer_credit_profiles SET status=?, credit_limit=?,"
            " payment_terms_days=?, risk_level=?, authorized_at=?, authorized_by_user_id=?,"
            " suspended_at=?, blocked_at=?, review_at=?, closed_at=?, close_reason=?,"
            " version=?, updated_at=? WHERE id=?",
            (profile.status.value, str(profile.credit_limit), profile.payment_terms_days,
             profile.risk_level.value, profile.authorized_at, profile.authorized_by_user_id,
             profile.suspended_at, profile.blocked_at, profile.review_at, profile.closed_at,
             profile.close_reason, profile.version, profile.updated_at, profile.id))

    def get(self, profile_id: str) -> CustomerCreditProfile | None:
        row = self._query_one(
            f"SELECT {_PROFILE_COLS} FROM customer_credit_profiles WHERE id=?", (profile_id,))
        return self._hydrate(row) if row else None

    def get_by_customer_id(self, customer_id: str) -> CustomerCreditProfile | None:
        row = self._query_one(
            f"SELECT {_PROFILE_COLS} FROM customer_credit_profiles WHERE customer_id=?",
            (customer_id,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> CustomerCreditProfile | None:
        row = self._query_one(
            f"SELECT {_PROFILE_COLS} FROM customer_credit_profiles WHERE operation_id=?",
            (operation_id,))
        return self._hydrate(row) if row else None

    def list_by_status(self, status: str, *,
                        limit: int = 200, offset: int = 0) -> list[CustomerCreditProfile]:
        rows = self._query(
            f"SELECT {_PROFILE_COLS} FROM customer_credit_profiles WHERE status=?"
            " ORDER BY updated_at DESC LIMIT ? OFFSET ?", (status, limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(profile: CustomerCreditProfile, operation_id: str | None) -> tuple:
        return (
            profile.id, profile.customer_id, profile.status.value, str(profile.credit_limit),
            profile.payment_terms_days, profile.risk_level.value, profile.requested_by_user_id,
            profile.authorized_at, profile.authorized_by_user_id, profile.suspended_at,
            profile.blocked_at, profile.review_at, profile.closed_at, profile.close_reason,
            profile.version, operation_id, profile.created_at, profile.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerCreditProfile:
        return CustomerCreditProfile(
            id=row["id"], customer_id=row["customer_id"], status=CreditProfileStatus(row["status"]),
            credit_limit=Decimal(row["credit_limit"]), payment_terms_days=row["payment_terms_days"],
            risk_level=CreditRiskLevel(row["risk_level"]),
            requested_by_user_id=row["requested_by_user_id"], authorized_at=row["authorized_at"],
            authorized_by_user_id=row["authorized_by_user_id"], suspended_at=row["suspended_at"],
            blocked_at=row["blocked_at"], review_at=row["review_at"], closed_at=row["closed_at"],
            close_reason=row["close_reason"] or "", version=row["version"],
            operation_id=row["operation_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
