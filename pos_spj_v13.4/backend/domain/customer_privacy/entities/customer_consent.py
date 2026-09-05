"""CustomerConsent — one evidence record of a consent decision (§44). "No
inferir consentimiento por tener teléfono/correo" — a record here only
exists because someone (customer or staff on the customer's behalf)
explicitly captured/withdrew it, never derived from other data.

Status transitions:

    request() ──► PENDING ──confirm()──► GRANTED ──withdraw(reason)──► WITHDRAWN
    capture() ──► GRANTED directly (explicit synchronous capture — the
                  common path: a checkbox was ticked, a verbal consent was
                  recorded, at some point *before* this call)
    mark_not_required() ──► NOT_REQUIRED (this consent type doesn't apply
                  to this customer/account)

``effective_status()`` derives EXPIRED without ever persisting it — see
ConsentStatus's docstring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_privacy.enums import ConsentChannel, ConsentStatus, ConsentType
from backend.domain.customer_privacy.exceptions import InvalidCustomerConsentStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_CONFIRMABLE = {ConsentStatus.PENDING}
_WITHDRAWABLE = {ConsentStatus.GRANTED}


@dataclass(slots=True)
class CustomerConsent:
    id: str
    customer_id: str
    consent_type: ConsentType
    status: ConsentStatus
    channel: ConsentChannel = ConsentChannel.OTHER
    evidence_reference: str = ""
    captured_by_user_id: str | None = None
    granted_at: str | None = None
    withdrawn_at: str | None = None
    withdrawal_reason: str = ""
    expires_at: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    @classmethod
    def capture(
        cls, customer_id: str, consent_type: ConsentType, *,
        channel: ConsentChannel = ConsentChannel.OTHER, evidence_reference: str = "",
        captured_by_user_id: str | None = None, expires_at: str | None = None,
        operation_id: str | None = None,
    ) -> "CustomerConsent":
        if not customer_id:
            raise InvalidCustomerConsentStateError("customer_id es obligatorio")
        if not evidence_reference.strip():
            raise InvalidCustomerConsentStateError(
                "capture() requiere evidence_reference (no se infiere consentimiento)")
        return cls(
            id=new_uuid(), customer_id=customer_id, consent_type=consent_type,
            status=ConsentStatus.GRANTED, channel=channel, evidence_reference=evidence_reference,
            captured_by_user_id=captured_by_user_id, granted_at=_utcnow(), expires_at=expires_at,
            operation_id=operation_id,
        )

    @classmethod
    def request(
        cls, customer_id: str, consent_type: ConsentType, *,
        channel: ConsentChannel = ConsentChannel.OTHER, captured_by_user_id: str | None = None,
        operation_id: str | None = None,
    ) -> "CustomerConsent":
        if not customer_id:
            raise InvalidCustomerConsentStateError("customer_id es obligatorio")
        return cls(
            id=new_uuid(), customer_id=customer_id, consent_type=consent_type,
            status=ConsentStatus.PENDING, channel=channel,
            captured_by_user_id=captured_by_user_id, operation_id=operation_id,
        )

    @classmethod
    def decline(
        cls, customer_id: str, consent_type: ConsentType, *, reason: str,
        channel: ConsentChannel = ConsentChannel.OTHER, captured_by_user_id: str | None = None,
        operation_id: str | None = None,
    ) -> "CustomerConsent":
        """WA-14 (canal WhatsApp): un cliente puede declarar explícitamente
        que NO quiere este consentimiento sin que exista un `GRANTED`
        previo que retirar (p. ej. responde "BAJA" a un número con el que
        nunca había interactuado antes por WhatsApp) — `withdraw()` no
        cubre este caso porque exige partir de `GRANTED`
        (`_WITHDRAWABLE`). Va directo a `WITHDRAWN`, igual de explícito y
        evidenciado que `capture()` (exige `reason`, nunca se infiere)."""
        if not customer_id:
            raise InvalidCustomerConsentStateError("customer_id es obligatorio")
        if not reason.strip():
            raise InvalidCustomerConsentStateError("decline() requiere un motivo (no se infiere)")
        return cls(
            id=new_uuid(), customer_id=customer_id, consent_type=consent_type,
            status=ConsentStatus.WITHDRAWN, channel=channel, withdrawal_reason=reason,
            withdrawn_at=_utcnow(), captured_by_user_id=captured_by_user_id,
            operation_id=operation_id,
        )

    @classmethod
    def mark_not_required(
        cls, customer_id: str, consent_type: ConsentType, *, reason: str = "",
        captured_by_user_id: str | None = None, operation_id: str | None = None,
    ) -> "CustomerConsent":
        if not customer_id:
            raise InvalidCustomerConsentStateError("customer_id es obligatorio")
        return cls(
            id=new_uuid(), customer_id=customer_id, consent_type=consent_type,
            status=ConsentStatus.NOT_REQUIRED, evidence_reference=reason,
            captured_by_user_id=captured_by_user_id, operation_id=operation_id,
        )

    def confirm(self, *, evidence_reference: str) -> None:
        if self.status not in _CONFIRMABLE:
            raise InvalidCustomerConsentStateError(
                f"No se puede confirmar desde {self.status.value}")
        if not evidence_reference.strip():
            raise InvalidCustomerConsentStateError("confirm() requiere evidence_reference")
        self.status = ConsentStatus.GRANTED
        self.evidence_reference = evidence_reference
        self.granted_at = _utcnow()
        self._touch()

    def withdraw(self, reason: str) -> None:
        if self.status not in _WITHDRAWABLE:
            raise InvalidCustomerConsentStateError(
                f"No se puede retirar desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerConsentStateError("Retirar consentimiento requiere un motivo")
        self.status = ConsentStatus.WITHDRAWN
        self.withdrawn_at = _utcnow()
        self.withdrawal_reason = reason
        self._touch()

    def effective_status(self, *, as_of: str | None = None) -> ConsentStatus:
        if self.status is ConsentStatus.GRANTED and self.expires_at:
            if (as_of or _utcnow()) > self.expires_at:
                return ConsentStatus.EXPIRED
        return self.status

    def is_active(self, *, as_of: str | None = None) -> bool:
        return self.effective_status(as_of=as_of) is ConsentStatus.GRANTED
