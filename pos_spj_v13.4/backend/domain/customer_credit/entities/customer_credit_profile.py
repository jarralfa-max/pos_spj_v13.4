"""CustomerCreditProfile — the CRM-8 aggregate root (§37-40).

Status transitions:

    (no row) ──request()──► PENDING_APPROVAL ──review()──► UNDER_REVIEW
                                    │                            │
                                    │                      approve() / reject(reason)
                                    │                            │
                                    └──reject(reason)──► CLOSED ◄─┘
                                                            ▲
                                            UNDER_REVIEW ──approve()──► AUTHORIZED
                                                                            │
                                    AUTHORIZED ──update_limit()──► AUTHORIZED (same status)
                                    AUTHORIZED ──suspend(reason)──► SUSPENDED
                                    {AUTHORIZED,SUSPENDED} ──block(reason)──► BLOCKED
                                    {SUSPENDED,BLOCKED} ──reopen(reason)──► AUTHORIZED
                                    {AUTHORIZED,SUSPENDED,BLOCKED} ──close(reason)──► CLOSED

``current_exposure``/``available_credit`` (§37-40 names them as profile
fields) are deliberately NOT stored here: §40 is explicit — "CxC: Finanzas
es dueño de documentos/vencimientos/pagos/saldo/reversos; CRM solo muestra
exposición/saldo/vencido/próximo vencimiento vía
CustomerAccountsReceivableSummaryQuery — no crear ledger financiero
paralelo." Nothing in this bounded context's workflow ever writes a sale or
a payment, so a stored `current_exposure` column would go stale the moment
Ventas books a sale or Finanzas records a payment — a value only this
context updates but never actually tracks the truth of is worse than no
value at all. `CustomerAccountsReceivableSummaryQuery` (application layer)
computes it live, read-only, from Finanzas' own `cuentas_por_cobrar`.

``rejected`` has no dedicated status — §37-40's literal state enum has no
REJECTED value, so ``reject()`` lands in CLOSED with ``close_reason``
recording it (documented on CreditProfileStatus).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.customer_credit.enums import CreditProfileStatus, CreditRiskLevel
from backend.domain.customer_credit.exceptions import InvalidCustomerCreditStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decimal(value) -> Decimal:
    if value is None:
        raise InvalidCustomerCreditStateError("El monto es obligatorio")
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidCustomerCreditStateError("El monto debe ser Decimal, nunca float")
    return Decimal(str(value))


_REVIEWABLE = {CreditProfileStatus.PENDING_APPROVAL}
_APPROVABLE = {CreditProfileStatus.UNDER_REVIEW}
_REJECTABLE = {CreditProfileStatus.PENDING_APPROVAL, CreditProfileStatus.UNDER_REVIEW}
_LIMIT_EDITABLE = {CreditProfileStatus.AUTHORIZED}
_SUSPENDABLE = {CreditProfileStatus.AUTHORIZED}
_BLOCKABLE = {CreditProfileStatus.AUTHORIZED, CreditProfileStatus.SUSPENDED}
_REOPENABLE = {CreditProfileStatus.SUSPENDED, CreditProfileStatus.BLOCKED}
_CLOSABLE = {CreditProfileStatus.AUTHORIZED, CreditProfileStatus.SUSPENDED,
             CreditProfileStatus.BLOCKED}
_TERMINAL = {CreditProfileStatus.CLOSED}


@dataclass(slots=True)
class CustomerCreditProfile:
    id: str
    customer_id: str
    status: CreditProfileStatus = CreditProfileStatus.PENDING_APPROVAL
    credit_limit: Decimal = field(default_factory=lambda: Decimal("0"))
    payment_terms_days: int = 0
    risk_level: CreditRiskLevel = CreditRiskLevel.MEDIUM
    requested_by_user_id: str | None = None
    authorized_at: str | None = None
    authorized_by_user_id: str | None = None
    suspended_at: str | None = None
    blocked_at: str | None = None
    review_at: str | None = None
    closed_at: str | None = None
    close_reason: str = ""
    version: int = 1
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.credit_limit = _decimal(self.credit_limit)

    @classmethod
    def request(
        cls, customer_id: str, requested_by_user_id: str, *, requested_limit=Decimal("0"),
        payment_terms_days: int = 0, operation_id: str | None = None,
    ) -> "CustomerCreditProfile":
        if not customer_id:
            raise InvalidCustomerCreditStateError("customer_id es obligatorio")
        if not requested_by_user_id:
            raise InvalidCustomerCreditStateError("requested_by_user_id es obligatorio")
        if payment_terms_days < 0:
            raise InvalidCustomerCreditStateError("payment_terms_days no puede ser negativo")
        return cls(
            id=new_uuid(), customer_id=customer_id, status=CreditProfileStatus.PENDING_APPROVAL,
            credit_limit=requested_limit, payment_terms_days=payment_terms_days,
            requested_by_user_id=requested_by_user_id, operation_id=operation_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def _bump_version(self) -> None:
        self.version += 1
        self._touch()

    # lifecycle ---------------------------------------------------------------
    def review(self, *, risk_level: CreditRiskLevel | None = None) -> None:
        if self.status not in _REVIEWABLE:
            raise InvalidCustomerCreditStateError(f"No se puede revisar desde {self.status.value}")
        self.status = CreditProfileStatus.UNDER_REVIEW
        self.review_at = _utcnow()
        if risk_level is not None:
            self.risk_level = risk_level
        self._bump_version()

    def approve(
        self, authorized_by_user_id: str, *, credit_limit=None, payment_terms_days: int | None = None,
        risk_level: CreditRiskLevel | None = None,
    ) -> None:
        if self.status not in _APPROVABLE:
            raise InvalidCustomerCreditStateError(f"No se puede aprobar desde {self.status.value}")
        if not authorized_by_user_id:
            raise InvalidCustomerCreditStateError("approve() requiere quién autoriza")
        if credit_limit is not None:
            self.credit_limit = _decimal(credit_limit)
        if self.credit_limit <= 0:
            raise InvalidCustomerCreditStateError("credit_limit debe ser mayor a cero al aprobar")
        if payment_terms_days is not None:
            if payment_terms_days < 0:
                raise InvalidCustomerCreditStateError("payment_terms_days no puede ser negativo")
            self.payment_terms_days = payment_terms_days
        if risk_level is not None:
            self.risk_level = risk_level
        self.status = CreditProfileStatus.AUTHORIZED
        self.authorized_at = _utcnow()
        self.authorized_by_user_id = authorized_by_user_id
        self._bump_version()

    def reject(self, reason: str) -> None:
        if self.status not in _REJECTABLE:
            raise InvalidCustomerCreditStateError(f"No se puede rechazar desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerCreditStateError("Rechazar requiere un motivo")
        self.status = CreditProfileStatus.CLOSED
        self.close_reason = reason
        self.closed_at = _utcnow()
        self._bump_version()

    def update_limit(self, new_limit, *, authorized_by_user_id: str) -> None:
        if self.status not in _LIMIT_EDITABLE:
            raise InvalidCustomerCreditStateError(
                f"No se puede modificar el límite desde {self.status.value}")
        if not authorized_by_user_id:
            raise InvalidCustomerCreditStateError("update_limit() requiere quién autoriza")
        limit = _decimal(new_limit)
        if limit <= 0:
            raise InvalidCustomerCreditStateError("credit_limit debe ser mayor a cero")
        self.credit_limit = limit
        self.authorized_by_user_id = authorized_by_user_id
        self._bump_version()

    def suspend(self, reason: str) -> None:
        if self.status not in _SUSPENDABLE:
            raise InvalidCustomerCreditStateError(f"No se puede suspender desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerCreditStateError("Suspender requiere un motivo")
        self.status = CreditProfileStatus.SUSPENDED
        self.suspended_at = _utcnow()
        self._bump_version()

    def block(self, reason: str) -> None:
        if self.status not in _BLOCKABLE:
            raise InvalidCustomerCreditStateError(f"No se puede bloquear desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerCreditStateError("Bloquear requiere un motivo")
        self.status = CreditProfileStatus.BLOCKED
        self.blocked_at = _utcnow()
        self._bump_version()

    def reopen(self, reason: str) -> None:
        if self.status not in _REOPENABLE:
            raise InvalidCustomerCreditStateError(f"No se puede reabrir desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerCreditStateError("Reabrir requiere un motivo")
        self.status = CreditProfileStatus.AUTHORIZED
        self.suspended_at = None
        self.blocked_at = None
        self._bump_version()

    def close(self, reason: str) -> None:
        if self.status not in _CLOSABLE:
            raise InvalidCustomerCreditStateError(f"No se puede cerrar desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerCreditStateError("Cerrar requiere un motivo")
        self.status = CreditProfileStatus.CLOSED
        self.close_reason = reason
        self.closed_at = _utcnow()
        self._bump_version()

    # capability checks -------------------------------------------------------
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def is_usable_for_credit_sale(self) -> bool:
        return self.status is CreditProfileStatus.AUTHORIZED
