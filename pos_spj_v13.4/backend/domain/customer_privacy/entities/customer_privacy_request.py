"""CustomerPrivacyRequest — a data-subject-rights request (§44). Aggregate
root; folio-bearing like every other case-shaped entity in this pipeline
(Lead/Opportunity/CustomerServiceCase).

Status transitions:

    RECEIVED ──validate()──► VALIDATING ──start_processing()──► IN_PROGRESS
                                                                      │
                                          ┌───────────────────────────┼──────────────┐
                                     complete(reason)          reject(reason)   cancel(reason)
                                          ▼                          ▼               ▼
                                     COMPLETED                  REJECTED        CANCELLED

``ANONYMIZATION``/``CANCELLATION`` (erasure) requests complete via a
separate, more tightly-gated path — ``AnonymizeCustomerUseCase``
(application layer) — not this entity's plain ``complete()``: §44 requires
"anonimización respeta obligaciones fiscales, ventas históricas, CxC,
auditoría, prevención de fraude, retención legal" and a second-approver
hot authorization (§74's extraordinary-action list names anonymization
explicitly). This entity only tracks the request's own status; it does not
implement anonymization itself — same split as ``Customer.mark_anonymized()``
(CRM-3), which was built with that exact division in mind.

``related_consent_id`` is optional — when a request's type is
``CONSENT_WITHDRAWAL``, it points at the ``CustomerConsent`` this request
is about, so completing it can withdraw that specific consent record in
the same use case call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_privacy.enums import PrivacyRequestStatus, PrivacyRequestType
from backend.domain.customer_privacy.exceptions import InvalidPrivacyRequestStateError
from backend.domain.customer_privacy.value_objects.privacy_request_code import (
    PrivacyRequestCode,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_VALIDATABLE = {PrivacyRequestStatus.RECEIVED}
_STARTABLE = {PrivacyRequestStatus.VALIDATING}
_COMPLETABLE = {PrivacyRequestStatus.IN_PROGRESS}
_REJECTABLE = {PrivacyRequestStatus.RECEIVED, PrivacyRequestStatus.VALIDATING,
               PrivacyRequestStatus.IN_PROGRESS}
_CANCELLABLE = {PrivacyRequestStatus.RECEIVED, PrivacyRequestStatus.VALIDATING,
                PrivacyRequestStatus.IN_PROGRESS}
_TERMINAL = {PrivacyRequestStatus.COMPLETED, PrivacyRequestStatus.REJECTED,
             PrivacyRequestStatus.CANCELLED}


@dataclass(slots=True)
class CustomerPrivacyRequest:
    id: str
    code: PrivacyRequestCode
    customer_id: str
    request_type: PrivacyRequestType
    description: str = ""
    status: PrivacyRequestStatus = PrivacyRequestStatus.RECEIVED
    related_consent_id: str | None = None
    logged_by_user_id: str | None = None
    validated_by_user_id: str | None = None
    processed_by_user_id: str | None = None
    resolution_notes: str = ""
    received_at: str = field(default_factory=_utcnow)
    validated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    rejected_at: str | None = None
    cancelled_at: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, code: PrivacyRequestCode, customer_id: str, request_type: PrivacyRequestType, *,
        description: str = "", related_consent_id: str | None = None,
        logged_by_user_id: str | None = None, operation_id: str | None = None,
    ) -> "CustomerPrivacyRequest":
        if not customer_id:
            raise InvalidPrivacyRequestStateError("customer_id es obligatorio")
        if request_type is PrivacyRequestType.CONSENT_WITHDRAWAL and not related_consent_id:
            raise InvalidPrivacyRequestStateError(
                "CONSENT_WITHDRAWAL requiere related_consent_id")
        return cls(
            id=new_uuid(), code=code, customer_id=customer_id, request_type=request_type,
            description=description, related_consent_id=related_consent_id,
            logged_by_user_id=logged_by_user_id, operation_id=operation_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def validate(self, validated_by_user_id: str) -> None:
        if self.status not in _VALIDATABLE:
            raise InvalidPrivacyRequestStateError(f"No se puede validar desde {self.status.value}")
        if not validated_by_user_id:
            raise InvalidPrivacyRequestStateError("validate() requiere quién valida")
        self.status = PrivacyRequestStatus.VALIDATING
        self.validated_by_user_id = validated_by_user_id
        self.validated_at = _utcnow()
        self._touch()

    def start_processing(self, processed_by_user_id: str) -> None:
        if self.status not in _STARTABLE:
            raise InvalidPrivacyRequestStateError(f"No se puede iniciar desde {self.status.value}")
        if not processed_by_user_id:
            raise InvalidPrivacyRequestStateError("start_processing() requiere quién procesa")
        self.status = PrivacyRequestStatus.IN_PROGRESS
        self.processed_by_user_id = processed_by_user_id
        self.started_at = _utcnow()
        self._touch()

    def complete(self, resolution_notes: str = "") -> None:
        if self.status not in _COMPLETABLE:
            raise InvalidPrivacyRequestStateError(f"No se puede completar desde {self.status.value}")
        self.status = PrivacyRequestStatus.COMPLETED
        self.resolution_notes = resolution_notes
        self.completed_at = _utcnow()
        self._touch()

    def reject(self, reason: str) -> None:
        if self.status not in _REJECTABLE:
            raise InvalidPrivacyRequestStateError(f"No se puede rechazar desde {self.status.value}")
        if not reason.strip():
            raise InvalidPrivacyRequestStateError("Rechazar requiere un motivo")
        self.status = PrivacyRequestStatus.REJECTED
        self.resolution_notes = reason
        self.rejected_at = _utcnow()
        self._touch()

    def cancel(self, reason: str) -> None:
        if self.status not in _CANCELLABLE:
            raise InvalidPrivacyRequestStateError(f"No se puede cancelar desde {self.status.value}")
        if not reason.strip():
            raise InvalidPrivacyRequestStateError("Cancelar requiere un motivo")
        self.status = PrivacyRequestStatus.CANCELLED
        self.resolution_notes = reason
        self.cancelled_at = _utcnow()
        self._touch()

    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def requires_anonymization_workflow(self) -> bool:
        return self.request_type in (PrivacyRequestType.ANONYMIZATION,
                                     PrivacyRequestType.CANCELLATION)
