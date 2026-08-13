"""CustomerConsentRepository — persists CustomerConsent evidence records
(append-only per (customer, type) — see entities/__init__.py). Mirrors
backend/infrastructure/db/repositories/customer_credit/customer_credit_profile_repository.py.
"""

from __future__ import annotations

from backend.domain.customer_privacy.entities.customer_consent import CustomerConsent
from backend.domain.customer_privacy.enums import ConsentChannel, ConsentStatus, ConsentType
from backend.infrastructure.db.repositories.customer_privacy.base import (
    CustomerPrivacyRepositoryBase,
)

_CONSENT_COLS = (
    "id, customer_id, consent_type, status, channel, evidence_reference,"
    " captured_by_user_id, granted_at, withdrawn_at, withdrawal_reason,"
    " expires_at, operation_id, created_at, updated_at"
)


class CustomerConsentRepository(CustomerPrivacyRepositoryBase):
    def save(self, consent: CustomerConsent, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_consents ({_CONSENT_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(consent, operation_id or consent.operation_id))

    def update(self, consent: CustomerConsent) -> None:
        self._execute(
            "UPDATE customer_consents SET status=?, evidence_reference=?, granted_at=?,"
            " withdrawn_at=?, withdrawal_reason=?, updated_at=? WHERE id=?",
            (consent.status.value, consent.evidence_reference, consent.granted_at,
             consent.withdrawn_at, consent.withdrawal_reason, consent.updated_at, consent.id))

    def get(self, consent_id: str) -> CustomerConsent | None:
        row = self._query_one(f"SELECT {_CONSENT_COLS} FROM customer_consents WHERE id=?",
                              (consent_id,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> CustomerConsent | None:
        row = self._query_one(
            f"SELECT {_CONSENT_COLS} FROM customer_consents WHERE operation_id=?",
            (operation_id,))
        return self._hydrate(row) if row else None

    def get_latest(self, customer_id: str, consent_type: str) -> CustomerConsent | None:
        # created_at has only second precision, so two captures in the same
        # second tie there — id (UUIDv7, time-ordered to sub-millisecond
        # precision) is the real, deterministic tiebreaker.
        row = self._query_one(
            f"SELECT {_CONSENT_COLS} FROM customer_consents"
            " WHERE customer_id=? AND consent_type=? ORDER BY created_at DESC, id DESC LIMIT 1",
            (customer_id, consent_type))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[CustomerConsent]:
        rows = self._query(
            f"SELECT {_CONSENT_COLS} FROM customer_consents"
            " WHERE customer_id=? ORDER BY created_at DESC, id DESC", (customer_id,))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(consent: CustomerConsent, operation_id: str | None) -> tuple:
        return (
            consent.id, consent.customer_id, consent.consent_type.value, consent.status.value,
            consent.channel.value, consent.evidence_reference, consent.captured_by_user_id,
            consent.granted_at, consent.withdrawn_at, consent.withdrawal_reason,
            consent.expires_at, operation_id, consent.created_at, consent.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerConsent:
        return CustomerConsent(
            id=row["id"], customer_id=row["customer_id"],
            consent_type=ConsentType(row["consent_type"]), status=ConsentStatus(row["status"]),
            channel=ConsentChannel(row["channel"]), evidence_reference=row["evidence_reference"] or "",
            captured_by_user_id=row["captured_by_user_id"], granted_at=row["granted_at"],
            withdrawn_at=row["withdrawn_at"], withdrawal_reason=row["withdrawal_reason"] or "",
            expires_at=row["expires_at"], operation_id=row["operation_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
