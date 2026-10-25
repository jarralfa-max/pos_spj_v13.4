"""Capital de socios, préstamos y retiros (§17).

Ninguno de estos movimientos es ingreso ni gasto operativo: una aportación es
capital, un préstamo es pasivo, un retiro reduce capital y el interés de un
préstamo es gasto financiero (otros gastos), separado del abono a principal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.enums import CapitalMovementKind
from backend.domain.finance.exceptions import FinanceDomainError, InsufficientOutstandingError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Loan:
    id: str
    lender_name: str
    principal_amount: Money
    outstanding_principal: Money
    start_date: date
    liability_account_id: str
    operation_id: str
    maturity_date: date | None = None
    status: str = "OPEN"
    created_by: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, lender_name: str, principal: Money, start_date: date,
               liability_account_id: str, operation_id: str, *,
               maturity_date: date | None = None, created_by: str | None = None) -> "Loan":
        if not (lender_name or "").strip():
            raise FinanceDomainError("El préstamo requiere al acreedor")
        if not principal.is_positive():
            raise FinanceDomainError("El principal debe ser mayor que cero")
        if maturity_date is not None and maturity_date < start_date:
            raise FinanceDomainError("El vencimiento no puede ser anterior al inicio")
        return cls(id=new_uuid(), lender_name=lender_name.strip(), principal_amount=principal,
                   outstanding_principal=principal, start_date=start_date,
                   liability_account_id=liability_account_id, operation_id=operation_id,
                   maturity_date=maturity_date, created_by=created_by)

    def repay(self, principal: Money) -> None:
        if self.status != "OPEN":
            raise FinanceDomainError(f"No se abona a un préstamo {self.status}")
        if not principal.is_positive():
            raise FinanceDomainError("El abono a principal debe ser mayor que cero")
        if principal > self.outstanding_principal:
            raise InsufficientOutstandingError(
                f"El abono de {principal.to_string()} excede el saldo del préstamo "
                f"({self.outstanding_principal.to_string()})")
        self.outstanding_principal = self.outstanding_principal.subtract(principal)
        if self.outstanding_principal.is_zero():
            self.status = "PAID"
        self.updated_at = _utcnow()


@dataclass(slots=True)
class CapitalTransaction:
    id: str
    kind: CapitalMovementKind
    amount: Money
    transaction_date: date
    treasury_account_id: str
    operation_id: str
    interest_amount: Money = None  # type: ignore[assignment]
    counterparty: str = ""
    loan_id: str | None = None
    financial_document_id: str | None = None
    journal_entry_id: str | None = None
    created_by: str | None = None
    branch_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.interest_amount is None:
            self.interest_amount = Money.zero(self.amount.currency_code)

    @classmethod
    def create(cls, kind: CapitalMovementKind, amount: Money, transaction_date: date,
               treasury_account_id: str, operation_id: str, *,
               interest_amount: Money | None = None, counterparty: str = "",
               loan_id: str | None = None, created_by: str | None = None,
               branch_id: str | None = None) -> "CapitalTransaction":
        if not amount.is_positive() and not (interest_amount and interest_amount.is_positive()):
            raise FinanceDomainError("El movimiento de capital debe ser mayor que cero")
        if kind in (CapitalMovementKind.LOAN_RECEIVED, CapitalMovementKind.LOAN_REPAYMENT) \
                and not loan_id:
            raise FinanceDomainError("Un movimiento de préstamo indica a qué préstamo")
        if interest_amount is not None and kind is not CapitalMovementKind.LOAN_REPAYMENT \
                and interest_amount.is_positive():
            raise FinanceDomainError("Sólo el pago de un préstamo lleva interés")
        return cls(id=new_uuid(), kind=kind, amount=amount, transaction_date=transaction_date,
                   treasury_account_id=treasury_account_id, operation_id=operation_id,
                   interest_amount=interest_amount, counterparty=(counterparty or "").strip(),
                   loan_id=loan_id, created_by=created_by, branch_id=branch_id)

    def cash_amount(self) -> Money:
        return self.amount.add(self.interest_amount)
