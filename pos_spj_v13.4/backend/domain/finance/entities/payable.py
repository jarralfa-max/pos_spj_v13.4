"""Payable, SupplierPayment and SupplierAdvance — accounts payable domain (§12).

Ciclo separado, nunca en un solo botón:

    crear obligación → programar pago → autorizar → ejecutar → conciliar

Un documento bloqueado por diferencia de recepción (validación de tres vías:
orden, recepción, factura) o en disputa no se paga hasta desbloquearse con
autorización y motivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.finance.enums import (
    OPEN_PAYABLE_STATUSES,
    PayableStatus,
    PaymentPriority,
    PurchaseDebitNature,
    SupplierAdvanceStatus,
    SupplierPaymentStatus,
)
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    InsufficientOutstandingError,
    PaymentAlreadyExecutedError,
    PaymentAuthorizationError,
    PaymentNotAuthorizedError,
    SupplierDocumentBlockedError,
)
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Payable:
    id: str
    supplier_id: str
    financial_document_id: str
    original_amount: Money
    outstanding_amount: Money
    issue_date: date
    operation_id: str
    due_date: date | None = None
    branch_id: str | None = None
    status: PayableStatus = PayableStatus.OPEN
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    row_version: int = 0  # control optimista (auditoría F18)
    priority: PaymentPriority = PaymentPriority.NORMAL
    payment_terms: str = ""
    debit_nature: PurchaseDebitNature = PurchaseDebitNature.INVENTORY
    purchase_order_id: str | None = None
    goods_receipt_id: str | None = None
    blocked: bool = False
    block_reason: str | None = None
    unblocked_by: str | None = None
    unblock_reason: str | None = None
    dispute_reason: str | None = None
    retention_amount: Money | None = None
    early_payment_discount_percent: Decimal | None = None
    early_payment_discount_until: date | None = None

    def __post_init__(self) -> None:
        if self.retention_amount is None:
            self.retention_amount = Money.zero(self.original_amount.currency_code)

    @classmethod
    def create(cls, supplier_id: str, financial_document_id: str, amount: Money,
               issue_date: date, operation_id: str, *,
               due_date: date | None = None, branch_id: str | None = None,
               priority: PaymentPriority = PaymentPriority.NORMAL, payment_terms: str = "",
               debit_nature: PurchaseDebitNature = PurchaseDebitNature.INVENTORY,
               purchase_order_id: str | None = None, goods_receipt_id: str | None = None,
               retention_amount: Money | None = None,
               early_payment_discount_percent: Decimal | None = None,
               early_payment_discount_until: date | None = None) -> "Payable":
        if not supplier_id:
            raise FinanceDomainError("La CxP requiere proveedor")
        if not amount.is_positive():
            raise FinanceDomainError("El importe de la CxP debe ser mayor que cero")
        if retention_amount is not None and (retention_amount.is_negative()
                                             or retention_amount > amount):
            raise FinanceDomainError("La retención va de cero al importe del documento")
        if early_payment_discount_percent is not None and not (
                Decimal("0") <= Decimal(early_payment_discount_percent) <= Decimal("100")):
            raise FinanceDomainError("El descuento por pronto pago va de 0 a 100 %")
        return cls(
            id=new_uuid(), supplier_id=supplier_id,
            financial_document_id=financial_document_id,
            original_amount=amount, outstanding_amount=amount,
            issue_date=issue_date, operation_id=operation_id,
            due_date=due_date, branch_id=branch_id, priority=priority,
            payment_terms=(payment_terms or "").strip(), debit_nature=debit_nature,
            purchase_order_id=purchase_order_id, goods_receipt_id=goods_receipt_id,
            retention_amount=retention_amount,
            early_payment_discount_percent=(Decimal(early_payment_discount_percent)
                                            if early_payment_discount_percent is not None
                                            else None),
            early_payment_discount_until=early_payment_discount_until,
        )

    # ── estado ────────────────────────────────────────────────────────────
    @property
    def is_open(self) -> bool:
        return self.status in OPEN_PAYABLE_STATUSES

    def _recompute(self, as_of: date | None = None) -> None:
        if self.outstanding_amount.is_zero():
            self.status = PayableStatus.PAID
        elif self.status is PayableStatus.DISPUTED:
            pass
        elif as_of is not None and self.due_date is not None and as_of > self.due_date:
            self.status = PayableStatus.OVERDUE
        elif self.outstanding_amount.amount == self.original_amount.amount:
            self.status = PayableStatus.OPEN
        else:
            self.status = PayableStatus.PARTIALLY_PAID
        self.updated_at = _utcnow()

    def assert_payable(self) -> None:
        if self.status is PayableStatus.CANCELLED:
            raise FinanceDomainError("No se paga una CxP cancelada")
        if self.blocked:
            raise SupplierDocumentBlockedError(
                f"El documento está bloqueado: {self.block_reason or 'diferencia de recepción'}. "
                "Requiere desbloqueo autorizado antes de pagarse")
        if self.status is PayableStatus.DISPUTED:
            raise SupplierDocumentBlockedError(
                f"El documento está en disputa: {self.dispute_reason}")

    def mark_payment_stage(self, stage: PayableStatus) -> None:
        """Refleja el pago en curso (programado / autorizado) en la obligación."""
        if stage not in (PayableStatus.SCHEDULED, PayableStatus.AUTHORIZED):
            raise FinanceDomainError(f"{stage.value} no es una etapa de pago")
        if self.outstanding_amount.is_zero() or self.status is PayableStatus.CANCELLED:
            return
        if self.status is PayableStatus.DISPUTED:
            return
        self.status = stage
        self.updated_at = _utcnow()

    def release_payment_stage(self, as_of: date | None = None) -> None:
        if self.status in (PayableStatus.SCHEDULED, PayableStatus.AUTHORIZED):
            self._recompute(as_of)

    def mark_overdue(self, as_of: date) -> bool:
        if self.status not in (PayableStatus.OPEN, PayableStatus.PARTIALLY_PAID):
            return False
        if self.due_date is None or as_of <= self.due_date or self.outstanding_amount.is_zero():
            return False
        self.status = PayableStatus.OVERDUE
        self.updated_at = _utcnow()
        return True

    # ── movimientos ──────────────────────────────────────────────────────
    def apply_payment(self, amount: Money, *, as_of: date | None = None) -> None:
        self.assert_payable()
        if not amount.is_positive():
            raise FinanceDomainError("El pago debe ser mayor que cero")
        if amount > self.outstanding_amount:
            raise InsufficientOutstandingError(
                f"El pago de {amount.to_string()} excede el saldo "
                f"{self.outstanding_amount.to_string()}")
        self.outstanding_amount = self.outstanding_amount.subtract(amount)
        self._recompute(as_of)

    def apply_credit_note(self, amount: Money) -> None:
        """Nota de crédito del proveedor: baja lo que se le debe; el excedente
        sería un anticipo a proveedor, nunca un saldo negativo."""
        if self.status is PayableStatus.CANCELLED:
            raise FinanceDomainError("No se acredita una CxP cancelada")
        if not amount.is_positive():
            raise FinanceDomainError("La nota de crédito debe ser mayor que cero")
        if amount > self.outstanding_amount:
            raise InsufficientOutstandingError(
                f"La nota de crédito de {amount.to_string()} excede el saldo "
                f"{self.outstanding_amount.to_string()}")
        self.outstanding_amount = self.outstanding_amount.subtract(amount)
        self._recompute()

    def early_payment_discount(self, payment_date: date, amount: Money) -> Money:
        """Descuento por pronto pago aplicable a ``amount`` si se paga a tiempo."""
        if (self.early_payment_discount_percent is None
                or self.early_payment_discount_until is None
                or payment_date > self.early_payment_discount_until):
            return Money.zero(amount.currency_code)
        return amount.multiply(self.early_payment_discount_percent / Decimal("100"))

    # ── bloqueo / disputa / cancelación ───────────────────────────────────
    def block(self, reason: str) -> None:
        if not (reason or "").strip():
            raise FinanceDomainError("El bloqueo exige el motivo")
        self.blocked = True
        self.block_reason = reason.strip()
        self.updated_at = _utcnow()

    def unblock(self, by: str, reason: str) -> None:
        if not self.blocked:
            raise FinanceDomainError("El documento no está bloqueado")
        if not (reason or "").strip() or not by:
            raise FinanceDomainError("Desbloquear exige usuario y motivo")
        self.blocked = False
        self.unblocked_by = by
        self.unblock_reason = reason.strip()
        self.updated_at = _utcnow()

    def dispute(self, reason: str) -> None:
        if not self.is_open or self.status is PayableStatus.DISPUTED:
            raise FinanceDomainError(f"No se disputa una CxP {self.status.value}")
        if not (reason or "").strip():
            raise FinanceDomainError("La disputa exige el motivo")
        self.status = PayableStatus.DISPUTED
        self.dispute_reason = reason.strip()
        self.updated_at = _utcnow()

    def resolve_dispute(self, as_of: date | None = None) -> None:
        if self.status is not PayableStatus.DISPUTED:
            raise FinanceDomainError("La CxP no está en disputa")
        self.status = PayableStatus.OPEN
        self._recompute(as_of)

    def cancel(self) -> None:
        if self.status is PayableStatus.PAID:
            raise FinanceDomainError(
                "Una CxP pagada no se cancela; use una nota de crédito del proveedor")
        self.status = PayableStatus.CANCELLED
        self.outstanding_amount = Money.zero(self.original_amount.currency_code)
        self.updated_at = _utcnow()


@dataclass(slots=True)
class SupplierPayment:
    """One supplier payment moving through schedule → authorize → execute → reconcile."""

    id: str
    payable_id: str
    supplier_id: str
    amount: Money
    scheduled_date: date
    treasury_account_id: str
    operation_id: str
    status: SupplierPaymentStatus = SupplierPaymentStatus.SCHEDULED
    scheduled_by: str | None = None
    authorized_by: str | None = None
    authorized_at: str | None = None
    executed_at: str | None = None
    executed_date: date | None = None
    journal_entry_id: str | None = None
    reconciled_at: str | None = None
    reference: str = ""
    branch_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    #: Evidencia de la ejecución (auditoría F13).
    executed_by: str | None = None
    execution_reference: str | None = None
    #: §28: pagos sobre el umbral exigen una segunda autorización distinta.
    second_authorization_required: bool = False
    second_authorized_by: str | None = None
    second_authorized_at: str | None = None
    #: Descuento por pronto pago tomado al ejecutar.
    discount_amount: Money | None = None

    def __post_init__(self) -> None:
        if self.discount_amount is None:
            self.discount_amount = Money.zero(self.amount.currency_code)

    @classmethod
    def schedule(cls, payable_id: str, supplier_id: str, amount: Money,
                 scheduled_date: date, treasury_account_id: str, operation_id: str,
                 *, scheduled_by: str | None = None, reference: str = "",
                 branch_id: str | None = None,
                 second_authorization_required: bool = False) -> "SupplierPayment":
        if not amount.is_positive():
            raise FinanceDomainError("El pago programado debe ser mayor que cero")
        if not treasury_account_id:
            raise FinanceDomainError("El pago programado requiere la cuenta de tesorería")
        return cls(
            id=new_uuid(), payable_id=payable_id, supplier_id=supplier_id,
            amount=amount, scheduled_date=scheduled_date,
            treasury_account_id=treasury_account_id, operation_id=operation_id,
            scheduled_by=scheduled_by, reference=reference, branch_id=branch_id,
            second_authorization_required=bool(second_authorization_required),
        )

    @property
    def is_fully_authorized(self) -> bool:
        return self.status is SupplierPaymentStatus.AUTHORIZED

    def authorize(self, authorized_by: str) -> bool:
        """Registra una autorización. Devuelve ``True`` si con ella el pago
        queda totalmente autorizado (AUTHORIZED)."""
        if self.status is not SupplierPaymentStatus.SCHEDULED:
            raise PaymentAuthorizationError(
                f"No se autoriza un pago {self.status.value}")
        who = (authorized_by or "").strip()
        if not who:
            raise PaymentAuthorizationError("La autorización requiere el usuario que autoriza")
        if self.scheduled_by and who == self.scheduled_by:
            raise PaymentAuthorizationError(
                "Segregación de funciones: quien programa un pago no lo autoriza")
        now = _utcnow()
        if self.authorized_by is None:
            self.authorized_by = who
            self.authorized_at = now
            if not self.second_authorization_required:
                self.status = SupplierPaymentStatus.AUTHORIZED
        else:
            if who == self.authorized_by:
                raise PaymentAuthorizationError(
                    "La segunda autorización la da una persona distinta de la primera")
            self.second_authorized_by = who
            self.second_authorized_at = now
            self.status = SupplierPaymentStatus.AUTHORIZED
        self.updated_at = now
        return self.status is SupplierPaymentStatus.AUTHORIZED

    def execute(self, executed_date: date, journal_entry_id: str, *,
                executed_by: str | None = None, execution_reference: str | None = None,
                discount_amount: Money | None = None) -> None:
        if self.status in (SupplierPaymentStatus.EXECUTED, SupplierPaymentStatus.RECONCILED):
            raise PaymentAlreadyExecutedError("El pago ya se ejecutó; no se paga dos veces")
        if self.status is not SupplierPaymentStatus.AUTHORIZED:
            raise PaymentNotAuthorizedError(
                "El pago no está autorizado"
                + (" (falta la segunda autorización)" if self.authorized_by else ""))
        self.executed_by = executed_by
        self.execution_reference = execution_reference
        self.status = SupplierPaymentStatus.EXECUTED
        self.executed_date = executed_date
        self.journal_entry_id = journal_entry_id
        if discount_amount is not None:
            self.discount_amount = discount_amount
        self.executed_at = _utcnow()
        self.updated_at = self.executed_at

    def reconcile(self) -> None:
        if self.status is not SupplierPaymentStatus.EXECUTED:
            raise FinanceDomainError(f"No se concilia un pago {self.status.value}")
        self.status = SupplierPaymentStatus.RECONCILED
        self.reconciled_at = _utcnow()
        self.updated_at = self.reconciled_at

    def cancel(self) -> None:
        if self.status in (SupplierPaymentStatus.EXECUTED, SupplierPaymentStatus.RECONCILED):
            raise FinanceDomainError("Un pago ejecutado no se cancela; registre un reverso")
        self.status = SupplierPaymentStatus.CANCELLED
        self.updated_at = _utcnow()


@dataclass(slots=True)
class SupplierAdvance:
    """Anticipo a proveedor: dinero entregado antes del documento; se aplica
    después contra una o varias CxP."""

    id: str
    supplier_id: str
    amount: Money
    advance_date: date
    treasury_account_id: str
    operation_id: str
    applied_amount: Money = None  # type: ignore[assignment]
    status: SupplierAdvanceStatus = SupplierAdvanceStatus.OPEN
    reference: str = ""
    branch_id: str | None = None
    journal_entry_id: str | None = None
    created_by: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.applied_amount is None:
            self.applied_amount = Money.zero(self.amount.currency_code)

    @classmethod
    def create(cls, supplier_id: str, amount: Money, advance_date: date,
               treasury_account_id: str, operation_id: str, *, reference: str = "",
               branch_id: str | None = None,
               created_by: str | None = None) -> "SupplierAdvance":
        if not supplier_id:
            raise FinanceDomainError("El anticipo requiere proveedor")
        if not amount.is_positive():
            raise FinanceDomainError("El anticipo debe ser mayor que cero")
        return cls(id=new_uuid(), supplier_id=supplier_id, amount=amount,
                   advance_date=advance_date, treasury_account_id=treasury_account_id,
                   operation_id=operation_id, reference=(reference or "").strip(),
                   branch_id=branch_id, created_by=created_by)

    def available(self) -> Money:
        return self.amount.subtract(self.applied_amount)

    def apply(self, amount: Money) -> None:
        if self.status is SupplierAdvanceStatus.CANCELLED:
            raise FinanceDomainError("No se aplica un anticipo cancelado")
        if not amount.is_positive() or amount > self.available():
            raise InsufficientOutstandingError(
                f"Aplicar {amount.to_string()} excede lo disponible del anticipo "
                f"({self.available().to_string()})")
        self.applied_amount = self.applied_amount.add(amount)
        self.status = (SupplierAdvanceStatus.APPLIED if self.available().is_zero()
                       else SupplierAdvanceStatus.PARTIALLY_APPLIED)
        self.updated_at = _utcnow()
