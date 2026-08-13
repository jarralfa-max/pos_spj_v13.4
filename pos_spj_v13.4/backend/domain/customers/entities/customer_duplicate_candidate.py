"""CustomerDuplicateCandidate — a detected likely-duplicate pair (§45).

Produced by DetectDuplicateCandidatesUseCase running
``CustomerDuplicatePolicy.find_matches()`` across the customer base and
persisting each match as a reviewable record (the policy itself never
persists — see its docstring). Never merges automatically; a human must
review, then either confirm (unlocking CustomerMergeRecord) or dismiss.

Status transitions:

    DETECTED ──start_review()──► UNDER_REVIEW ──confirm()──► CONFIRMED_DUPLICATE
                                       │
                                       └──dismiss(reason)──► DISMISSED

    CONFIRMED_DUPLICATE ──mark_merged()──► MERGED (set by
        ExecuteCustomerMergeUseCase once the merge actually runs — this
        entity does not implement merge logic itself, mirrors
        Customer.mark_merged()'s same division of responsibility)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customers.enums import DuplicateCandidateStatus
from backend.domain.customers.exceptions import InvalidDuplicateCandidateStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_REVIEWABLE = {DuplicateCandidateStatus.DETECTED}
_DISMISSIBLE = {DuplicateCandidateStatus.DETECTED, DuplicateCandidateStatus.UNDER_REVIEW}
_CONFIRMABLE = {DuplicateCandidateStatus.UNDER_REVIEW}
_MERGEABLE = {DuplicateCandidateStatus.CONFIRMED_DUPLICATE}


@dataclass(slots=True)
class CustomerDuplicateCandidate:
    id: str
    customer_id_a: str
    customer_id_b: str
    match_reasons: tuple[str, ...] = field(default_factory=tuple)
    status: DuplicateCandidateStatus = DuplicateCandidateStatus.DETECTED
    reviewed_by_user_id: str | None = None
    reviewed_at: str | None = None
    resolution_reason: str = ""
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    @classmethod
    def detect(
        cls, customer_id_a: str, customer_id_b: str, match_reasons: tuple[str, ...], *,
        operation_id: str | None = None,
    ) -> "CustomerDuplicateCandidate":
        if not customer_id_a or not customer_id_b:
            raise InvalidDuplicateCandidateStateError(
                "customer_id_a y customer_id_b son obligatorios")
        if customer_id_a == customer_id_b:
            raise InvalidDuplicateCandidateStateError(
                "Un cliente no puede ser candidato duplicado de sí mismo")
        if not match_reasons:
            raise InvalidDuplicateCandidateStateError(
                "match_reasons no puede estar vacío")
        return cls(id=new_uuid(), customer_id_a=customer_id_a, customer_id_b=customer_id_b,
                   match_reasons=tuple(match_reasons), operation_id=operation_id)

    def start_review(self, reviewed_by_user_id: str) -> None:
        if self.status not in _REVIEWABLE:
            raise InvalidDuplicateCandidateStateError(
                f"No se puede iniciar revisión desde {self.status.value}")
        self.status = DuplicateCandidateStatus.UNDER_REVIEW
        self.reviewed_by_user_id = reviewed_by_user_id
        self.reviewed_at = _utcnow()
        self._touch()

    def confirm(self) -> None:
        if self.status not in _CONFIRMABLE:
            raise InvalidDuplicateCandidateStateError(
                f"No se puede confirmar desde {self.status.value}")
        self.status = DuplicateCandidateStatus.CONFIRMED_DUPLICATE
        self._touch()

    def dismiss(self, reason: str) -> None:
        if self.status not in _DISMISSIBLE:
            raise InvalidDuplicateCandidateStateError(
                f"No se puede descartar desde {self.status.value}")
        if not reason.strip():
            raise InvalidDuplicateCandidateStateError("Descartar requiere un motivo")
        self.status = DuplicateCandidateStatus.DISMISSED
        self.resolution_reason = reason.strip()
        self._touch()

    def mark_merged(self) -> None:
        if self.status not in _MERGEABLE:
            raise InvalidDuplicateCandidateStateError(
                f"No se puede marcar fusionado desde {self.status.value}")
        self.status = DuplicateCandidateStatus.MERGED
        self._touch()

    def involves(self, customer_id: str) -> bool:
        return customer_id in (self.customer_id_a, self.customer_id_b)
