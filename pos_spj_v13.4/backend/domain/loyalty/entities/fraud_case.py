"""FraudCase — a suspected-fraud incident under review (master prompt §29).

``subject_id`` is an unchecked opaque reference — a case may point at a
Referral, a LoyaltyTransaction, a Membership, or a Commercial Instruments
coupon/voucher, or a Sweepstakes entry, none of which this entity resolves
or validates (same bounded-context-isolation discipline as every other
cross-context reference built in this pipeline: `CouponDefinition.
source_program_id`, LOY-12; `LoyaltyCard.membership_id`, LOY-16).

Segregation of duties (§60's own recurring rule, applied here the same way
as Campaigns/Templates/Batches elsewhere in this pipeline): whoever reviews
a case must be a different user from whoever opened it — "quien reporta el
fraude no lo resuelve solo".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty.enums import FraudCaseStatus, FraudCaseSubjectType
from backend.domain.loyalty.exceptions import (
    InvalidFraudCaseError,
    InvalidFraudCaseStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class FraudCase:
    id: str
    subject_type: FraudCaseSubjectType
    subject_id: str
    customer_id: str
    reason: str
    opened_by_user_id: str
    status: FraudCaseStatus = FraudCaseStatus.OPEN
    reviewed_by_user_id: str | None = None
    resolution_notes: str | None = None
    opened_at: str = field(default_factory=_utcnow)
    resolved_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.subject_id:
            raise InvalidFraudCaseError("subject_id es obligatorio")
        if not self.customer_id:
            raise InvalidFraudCaseError("customer_id es obligatorio")
        if not self.reason or not self.reason.strip():
            raise InvalidFraudCaseError("reason es obligatorio")
        if not self.opened_by_user_id:
            raise InvalidFraudCaseError("opened_by_user_id es obligatorio")

    @classmethod
    def open(cls, subject_type: FraudCaseSubjectType, subject_id: str, customer_id: str,
             reason: str, *, opened_by_user_id: str) -> "FraudCase":
        return cls(id=new_uuid(), subject_type=subject_type, subject_id=subject_id,
                   customer_id=customer_id, reason=reason.strip(),
                   opened_by_user_id=opened_by_user_id)

    def start_review(self, reviewer_user_id: str) -> None:
        if self.status is not FraudCaseStatus.OPEN:
            raise InvalidFraudCaseStateError(
                f"Solo se inicia revisión desde OPEN (actual: {self.status.value})")
        if reviewer_user_id == self.opened_by_user_id:
            raise InvalidFraudCaseStateError(
                "Quien revisa el caso debe ser distinto de quien lo reportó "
                "(segregación de funciones)")
        self.status = FraudCaseStatus.UNDER_REVIEW
        self.reviewed_by_user_id = reviewer_user_id
        self.updated_at = _utcnow()

    def confirm(self, resolution_notes: str) -> None:
        if self.status is not FraudCaseStatus.UNDER_REVIEW:
            raise InvalidFraudCaseStateError(
                f"Solo se confirma desde UNDER_REVIEW (actual: {self.status.value})")
        if not (resolution_notes or "").strip():
            raise InvalidFraudCaseStateError("Confirmar el caso requiere notas de resolución")
        self.status = FraudCaseStatus.CONFIRMED
        self.resolution_notes = resolution_notes.strip()
        self.resolved_at = _utcnow()
        self.updated_at = _utcnow()

    def dismiss(self, resolution_notes: str) -> None:
        if self.status is not FraudCaseStatus.UNDER_REVIEW:
            raise InvalidFraudCaseStateError(
                f"Solo se descarta desde UNDER_REVIEW (actual: {self.status.value})")
        if not (resolution_notes or "").strip():
            raise InvalidFraudCaseStateError("Descartar el caso requiere notas de resolución")
        self.status = FraudCaseStatus.DISMISSED
        self.resolution_notes = resolution_notes.strip()
        self.resolved_at = _utcnow()
        self.updated_at = _utcnow()

    def is_open(self) -> bool:
        return self.status in (FraudCaseStatus.OPEN, FraudCaseStatus.UNDER_REVIEW)
