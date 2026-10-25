"""Receivable, Collection and CollectionApplication — accounts receivable domain (§11).

- Una CxC no se marca cobrada por registrar un ingreso: el cobro se APLICA
  explícitamente a uno o varios documentos.
- suma aplicada ≤ importe del cobro y suma aplicada ≤ saldo de cada CxC.
- Lo no aplicado de un cobro es saldo a favor del cliente (anticipo de clientes).
- Castigo y cancelación dejan el saldo en cero con su asiento; nunca se borra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.enums import (
    CollectionStatus,
    OPEN_RECEIVABLE_STATUSES,
    ReceivableStatus,
)
from backend.domain.finance.exceptions import (
    CollectionAmountExceededError,
    FinanceDomainError,
    InsufficientOutstandingError,
)
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_CLOSED = (ReceivableStatus.CANCELLED, ReceivableStatus.WRITTEN_OFF)


@dataclass(slots=True)
class Receivable:
    id: str
    customer_id: str
    financial_document_id: str
    original_amount: Money
    outstanding_amount: Money
    issue_date: date
    operation_id: str
    due_date: date | None = None
    branch_id: str | None = None
    status: ReceivableStatus = ReceivableStatus.OPEN
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    #: Versión leída (control optimista, auditoría F18).
    row_version: int = 0
    credit_term_days: int | None = None
    credit_origin: str = "SALE"
    dispute_reason: str | None = None
    disputed_at: str | None = None
    disputed_by: str | None = None
    written_off_at: str | None = None
    written_off_by: str | None = None
    write_off_reason: str | None = None

    @classmethod
    def create(cls, customer_id: str, financial_document_id: str, amount: Money,
               issue_date: date, operation_id: str, *,
               due_date: date | None = None, branch_id: str | None = None,
               credit_term_days: int | None = None,
               credit_origin: str = "SALE") -> "Receivable":
        if not customer_id:
            raise FinanceDomainError("La CxC requiere cliente")
        if not amount.is_positive():
            raise FinanceDomainError("El importe de la CxC debe ser mayor que cero")
        if credit_term_days is not None and credit_term_days < 0:
            raise FinanceDomainError("El plazo de crédito no puede ser negativo")
        return cls(
            id=new_uuid(), customer_id=customer_id,
            financial_document_id=financial_document_id,
            original_amount=amount, outstanding_amount=amount,
            issue_date=issue_date, operation_id=operation_id,
            due_date=due_date, branch_id=branch_id,
            credit_term_days=credit_term_days, credit_origin=(credit_origin or "SALE").upper(),
        )

    # ── estado ────────────────────────────────────────────────────────────
    @property
    def is_open(self) -> bool:
        return self.status in OPEN_RECEIVABLE_STATUSES

    def _settle_status(self) -> None:
        if self.outstanding_amount.is_zero():
            self.status = ReceivableStatus.COLLECTED
        elif self.status in (ReceivableStatus.OVERDUE, ReceivableStatus.DISPUTED):
            pass  # sigue vencida / en disputa hasta liquidarse o resolverse
        elif self.outstanding_amount.amount == self.original_amount.amount:
            self.status = ReceivableStatus.OPEN
        else:
            self.status = ReceivableStatus.PARTIALLY_COLLECTED
        self.updated_at = _utcnow()

    def _assert_not_closed(self, action: str) -> None:
        if self.status in _CLOSED:
            raise FinanceDomainError(f"No se puede {action} una CxC {self.status.value}")

    # ── cargos (Ventas F03 / V02) ─────────────────────────────────────────
    def add_charge(self, amount: Money) -> None:
        """Otro cargo a crédito sobre el mismo documento (auditoría F03)."""
        self._assert_not_closed("cargar")
        if not amount.is_positive():
            raise FinanceDomainError("El cargo debe ser mayor que cero")
        self.original_amount = self.original_amount.add(amount)
        self.outstanding_amount = self.outstanding_amount.add(amount)
        if self.status is ReceivableStatus.COLLECTED:
            self.status = ReceivableStatus.PARTIALLY_COLLECTED
        self._settle_status()

    def remove_charge(self, amount: Money) -> None:
        """Retira un cargo a crédito anulado antes de cerrar la venta (V02)."""
        self._assert_not_closed("ajustar")
        if not amount.is_positive():
            raise FinanceDomainError("El cargo debe ser mayor que cero")
        if amount > self.outstanding_amount:
            raise InsufficientOutstandingError(
                f"El cargo {amount.to_string()} excede el saldo "
                f"{self.outstanding_amount.to_string()}")
        self.original_amount = self.original_amount.subtract(amount)
        self.outstanding_amount = self.outstanding_amount.subtract(amount)
        if self.original_amount.is_zero():
            self.status = ReceivableStatus.CANCELLED
            self.updated_at = _utcnow()
            return
        self._settle_status()

    # ── cobranza ──────────────────────────────────────────────────────────
    def apply_collection(self, amount: Money) -> None:
        self._assert_not_closed("cobrar")
        if not amount.is_positive():
            raise FinanceDomainError("La aplicación debe ser mayor que cero")
        if amount > self.outstanding_amount:
            raise CollectionAmountExceededError(
                f"La aplicación de {amount.to_string()} excede el saldo por cobrar "
                f"{self.outstanding_amount.to_string()}")
        self.outstanding_amount = self.outstanding_amount.subtract(amount)
        self._settle_status()

    def apply_credit_note(self, amount: Money) -> None:
        """Nota de crédito: baja lo que el cliente debe. Si excede el saldo, el
        excedente es saldo a favor (otro instrumento), no un saldo negativo."""
        self._assert_not_closed("acreditar")
        if not amount.is_positive():
            raise FinanceDomainError("La nota de crédito debe ser mayor que cero")
        if amount > self.outstanding_amount:
            raise InsufficientOutstandingError(
                f"La nota de crédito de {amount.to_string()} excede el saldo "
                f"{self.outstanding_amount.to_string()}")
        self.outstanding_amount = self.outstanding_amount.subtract(amount)
        self._settle_status()

    # ── vencimiento / disputa / castigo / cancelación ─────────────────────
    def days_overdue(self, as_of: date) -> int:
        if self.due_date is None or self.outstanding_amount.is_zero():
            return 0
        return max(0, (as_of - self.due_date).days)

    def mark_overdue(self, as_of: date) -> bool:
        """OPEN/PARTIALLY_COLLECTED vencida → OVERDUE. Devuelve si cambió."""
        if self.status not in (ReceivableStatus.OPEN, ReceivableStatus.PARTIALLY_COLLECTED):
            return False
        if self.days_overdue(as_of) <= 0:
            return False
        self.status = ReceivableStatus.OVERDUE
        self.updated_at = _utcnow()
        return True

    def dispute(self, reason: str, by: str) -> None:
        if not self.is_open or self.status is ReceivableStatus.DISPUTED:
            raise FinanceDomainError(f"No se disputa una CxC {self.status.value}")
        if not (reason or "").strip():
            raise FinanceDomainError("La disputa exige el motivo")
        self.status = ReceivableStatus.DISPUTED
        self.dispute_reason = reason.strip()
        self.disputed_at = _utcnow()
        self.disputed_by = by
        self.updated_at = self.disputed_at

    def resolve_dispute(self, as_of: date) -> None:
        if self.status is not ReceivableStatus.DISPUTED:
            raise FinanceDomainError("La CxC no está en disputa")
        self.status = (ReceivableStatus.OPEN
                       if self.outstanding_amount.amount == self.original_amount.amount
                       else ReceivableStatus.PARTIALLY_COLLECTED)
        self.mark_overdue(as_of)
        self.updated_at = _utcnow()

    def write_off(self, reason: str, by: str) -> Money:
        """Castigo: devuelve el saldo castigado (para su asiento) y lo deja en cero."""
        if not self.is_open:
            raise FinanceDomainError(f"No se castiga una CxC {self.status.value}")
        if not (reason or "").strip():
            raise FinanceDomainError("El castigo exige el motivo")
        amount = self.outstanding_amount
        self.outstanding_amount = Money.zero(amount.currency_code)
        self.status = ReceivableStatus.WRITTEN_OFF
        self.written_off_at = _utcnow()
        self.written_off_by = by
        self.write_off_reason = reason.strip()
        self.updated_at = self.written_off_at
        return amount

    def cancel(self) -> None:
        if self.status is ReceivableStatus.COLLECTED:
            raise FinanceDomainError(
                "Una CxC cobrada no se cancela; use una nota de crédito")
        self.status = ReceivableStatus.CANCELLED
        self.outstanding_amount = Money.zero(self.original_amount.currency_code)
        self.updated_at = _utcnow()


@dataclass(slots=True)
class Collection:
    """Un pago recibido del cliente, que se aplica a uno o varios documentos."""

    id: str
    customer_id: str
    amount: Money
    collection_date: date
    treasury_account_id: str
    operation_id: str
    applied_amount: Money = None  # type: ignore[assignment]
    payment_method: str = "BANK_TRANSFER"
    status: CollectionStatus = CollectionStatus.UNAPPLIED
    journal_entry_id: str | None = None
    reference: str = ""
    branch_id: str | None = None
    created_by: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.applied_amount is None:
            self.applied_amount = Money.zero(self.amount.currency_code)

    @classmethod
    def create(cls, customer_id: str, amount: Money, collection_date: date,
               treasury_account_id: str, operation_id: str, *, reference: str = "",
               branch_id: str | None = None, payment_method: str = "BANK_TRANSFER",
               created_by: str | None = None) -> "Collection":
        if not customer_id:
            raise FinanceDomainError("El cobro requiere cliente")
        if not amount.is_positive():
            raise FinanceDomainError("El cobro debe ser mayor que cero")
        if not treasury_account_id:
            raise FinanceDomainError("El cobro requiere la cuenta de tesorería que lo recibe")
        return cls(
            id=new_uuid(), customer_id=customer_id, amount=amount,
            collection_date=collection_date, treasury_account_id=treasury_account_id,
            operation_id=operation_id, reference=(reference or "").strip(),
            branch_id=branch_id, payment_method=(payment_method or "BANK_TRANSFER").upper(),
            created_by=created_by,
        )

    def unapplied(self) -> Money:
        return self.amount.subtract(self.applied_amount)

    def register_application(self, amount: Money) -> None:
        if self.status is CollectionStatus.REVERSED:
            raise FinanceDomainError("Un cobro revertido no se aplica")
        if not amount.is_positive():
            raise FinanceDomainError("La aplicación debe ser mayor que cero")
        if amount > self.unapplied():
            raise CollectionAmountExceededError(
                f"Aplicar {amount.to_string()} excede lo disponible del cobro "
                f"({self.unapplied().to_string()})")
        self.applied_amount = self.applied_amount.add(amount)
        self.status = (CollectionStatus.APPLIED if self.unapplied().is_zero()
                       else CollectionStatus.PARTIALLY_APPLIED)
        self.updated_at = _utcnow()


@dataclass(slots=True)
class CollectionApplication:
    id: str
    collection_id: str
    receivable_id: str
    applied_amount: Money
    operation_id: str
    journal_entry_id: str | None = None
    created_by: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, collection_id: str, receivable_id: str, amount: Money,
               operation_id: str, *, created_by: str | None = None) -> "CollectionApplication":
        if not amount.is_positive():
            raise FinanceDomainError("La aplicación debe ser mayor que cero")
        return cls(id=new_uuid(), collection_id=collection_id, receivable_id=receivable_id,
                   applied_amount=amount, operation_id=operation_id, created_by=created_by)


@dataclass(slots=True)
class PaymentPromise:
    """Promesa de pago del cliente sobre una CxC (seguimiento de cobranza)."""

    id: str
    receivable_id: str
    promised_date: date
    promised_amount: Money
    operation_id: str
    note: str = ""
    status: str = "OPEN"
    created_by: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, receivable_id: str, promised_date: date, promised_amount: Money,
               operation_id: str, *, note: str = "",
               created_by: str | None = None) -> "PaymentPromise":
        if not promised_amount.is_positive():
            raise FinanceDomainError("La promesa de pago debe ser mayor que cero")
        return cls(id=new_uuid(), receivable_id=receivable_id, promised_date=promised_date,
                   promised_amount=promised_amount, operation_id=operation_id,
                   note=(note or "").strip(), created_by=created_by)

    def close(self, kept: bool) -> None:
        if self.status != "OPEN":
            raise FinanceDomainError(f"La promesa ya está {self.status}")
        self.status = "KEPT" if kept else "BROKEN"
        self.updated_at = _utcnow()
