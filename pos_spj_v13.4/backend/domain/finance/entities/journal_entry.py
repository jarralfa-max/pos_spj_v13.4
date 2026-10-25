"""JournalEntry aggregate — double-entry accounting entry with lines (§8.3).

Invariants:
- Every NORMAL line carries exactly one positive side (debit XOR credit), in
  the entry currency, and the same side in base currency.
- A ROUNDING line carries only a base-currency amount: the rounding difference
  of a conversion goes VISIBLE to its configured account (§24).
- A VALIDATED/POSTED entry satisfies Σdebits == Σcredits in base currency and,
  for its NORMAL lines, in the entry currency.
- A POSTED entry is immutable; corrections happen only via reversal entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.finance.enums import JournalEntryStatus, LineRole
from backend.domain.finance.exceptions import (
    EmptyEntryError,
    InvalidEntryStateError,
    JournalEntryAlreadyPostedError,
    JournalEntryImmutableError,
    UnbalancedJournalEntryError,
)
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Dimensiones analíticas que una línea puede llevar (§8.3, §23).
LINE_DIMENSIONS = ("cost_center_id", "profit_center_id", "branch_id", "project_id",
                   "department_id", "customer_id", "supplier_id", "employee_id",
                   "product_id")


@dataclass(slots=True)
class JournalLine:
    id: str
    journal_entry_id: str
    account_id: str
    description: str
    debit: Money
    credit: Money
    cost_center_id: str | None = None
    profit_center_id: str | None = None
    branch_id: str | None = None
    line_index: int = 0
    exchange_rate: Decimal = Decimal("1")
    base_debit: Money | None = None
    base_credit: Money | None = None
    line_role: LineRole = LineRole.NORMAL
    project_id: str | None = None
    department_id: str | None = None
    customer_id: str | None = None
    supplier_id: str | None = None
    employee_id: str | None = None
    product_id: str | None = None
    source_reference: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.exchange_rate, float):
            raise EmptyEntryError("El tipo de cambio no puede ser float")
        if not isinstance(self.exchange_rate, Decimal):
            self.exchange_rate = Decimal(str(self.exchange_rate))
        if self.base_debit is None:
            self.base_debit = self.debit
        if self.base_credit is None:
            self.base_credit = self.credit

    @property
    def currency_code(self) -> str:
        return self.debit.currency_code

    @classmethod
    def debit_line(cls, journal_entry_id: str, account_id: str, amount: Money,
                   description: str = "", *, base_amount: Money | None = None,
                   **kwargs) -> "JournalLine":
        base = base_amount or amount
        return cls(
            id=new_uuid(), journal_entry_id=journal_entry_id, account_id=account_id,
            description=description, debit=amount, credit=Money.zero(amount.currency_code),
            base_debit=base, base_credit=Money.zero(base.currency_code), **kwargs,
        )

    @classmethod
    def credit_line(cls, journal_entry_id: str, account_id: str, amount: Money,
                    description: str = "", *, base_amount: Money | None = None,
                    **kwargs) -> "JournalLine":
        base = base_amount or amount
        return cls(
            id=new_uuid(), journal_entry_id=journal_entry_id, account_id=account_id,
            description=description, debit=Money.zero(amount.currency_code), credit=amount,
            base_debit=Money.zero(base.currency_code), base_credit=base, **kwargs,
        )

    def validate(self) -> None:
        if not self.account_id:
            raise EmptyEntryError("Cada línea requiere una cuenta")
        for amount in (self.debit, self.credit, self.base_debit, self.base_credit):
            if amount.is_negative():
                raise EmptyEntryError("Los importes de una línea no pueden ser negativos")
        if self.exchange_rate <= 0:
            raise EmptyEntryError("El tipo de cambio debe ser mayor que cero")
        if self.base_debit.is_zero() == self.base_credit.is_zero():
            raise EmptyEntryError(
                "Cada línea lleva exactamente un lado positivo (débito o crédito, nunca ambos)")
        if self.line_role is LineRole.ROUNDING:
            if not (self.debit.is_zero() and self.credit.is_zero()):
                raise EmptyEntryError("Una línea de redondeo sólo lleva importe en moneda base")
            return
        if self.debit.is_zero() == self.credit.is_zero():
            raise EmptyEntryError(
                "Cada línea lleva exactamente un lado positivo (débito o crédito, nunca ambos)")
        if self.debit.is_positive() != self.base_debit.is_positive():
            raise EmptyEntryError("El lado en moneda base no coincide con el de la operación")

    def dimensions(self) -> dict[str, str | None]:
        return {name: getattr(self, name) for name in LINE_DIMENSIONS}


@dataclass(slots=True)
class JournalEntry:
    id: str
    journal_id: str
    entry_number: str
    entry_date: date
    fiscal_period_id: str
    description: str
    currency_code: str
    posting_reference: PostingReference
    branch_id: str | None = None
    status: JournalEntryStatus = JournalEntryStatus.DRAFT
    reversal_of_entry_id: str | None = None
    reversed_by_entry_id: str | None = None
    posted_at: str | None = None
    created_by: str | None = None
    lines: list[JournalLine] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    base_currency_code: str | None = None
    posting_date: date | None = None
    source_document_type: str | None = None
    validated_by: str | None = None
    validated_at: str | None = None
    posted_by: str | None = None
    cancelled_by: str | None = None
    cancel_reason: str | None = None

    def __post_init__(self) -> None:
        if self.base_currency_code is None:
            self.base_currency_code = self.currency_code
        if self.posting_date is None:
            self.posting_date = self.entry_date

    # ── construction ──────────────────────────────────────────────────────
    @classmethod
    def create(
        cls,
        journal_id: str,
        entry_number: str,
        entry_date: date,
        fiscal_period_id: str,
        description: str,
        posting_reference: PostingReference,
        *,
        currency_code: str = "MXN",
        base_currency_code: str | None = None,
        branch_id: str | None = None,
        created_by: str | None = None,
        reversal_of_entry_id: str | None = None,
        source_document_type: str | None = None,
    ) -> "JournalEntry":
        return cls(
            id=new_uuid(),
            journal_id=journal_id,
            entry_number=entry_number,
            entry_date=entry_date,
            fiscal_period_id=fiscal_period_id,
            description=description,
            currency_code=currency_code.upper(),
            base_currency_code=(base_currency_code or currency_code).upper(),
            posting_reference=posting_reference,
            branch_id=branch_id,
            created_by=created_by,
            reversal_of_entry_id=reversal_of_entry_id,
            source_document_type=source_document_type,
        )

    def add_debit(self, account_id: str, amount: Money, description: str = "",
                  **kwargs) -> JournalLine:
        self._assert_mutable()
        line = JournalLine.debit_line(self.id, account_id, amount, description,
                                      line_index=len(self.lines), **kwargs)
        self.lines.append(line)
        return line

    def add_credit(self, account_id: str, amount: Money, description: str = "",
                   **kwargs) -> JournalLine:
        self._assert_mutable()
        line = JournalLine.credit_line(self.id, account_id, amount, description,
                                       line_index=len(self.lines), **kwargs)
        self.lines.append(line)
        return line

    def add_rounding(self, account_id: str, base_amount: Money, *, debit: bool) -> JournalLine:
        """Diferencia de redondeo de la conversión: sólo moneda base, cuenta propia."""
        self._assert_mutable()
        zero = Money.zero(self.currency_code)
        base_zero = Money.zero(base_amount.currency_code)
        line = JournalLine(
            id=new_uuid(), journal_entry_id=self.id, account_id=account_id,
            description="Diferencia de redondeo por conversión",
            debit=zero, credit=zero,
            base_debit=base_amount if debit else base_zero,
            base_credit=base_zero if debit else base_amount,
            line_role=LineRole.ROUNDING, line_index=len(self.lines),
        )
        self.lines.append(line)
        return line

    def replace_lines(self, lines: list[JournalLine]) -> None:
        """Un borrador se corrige reemplazando sus líneas; nada más lo permite."""
        self._assert_mutable()
        self.lines = []
        for index, line in enumerate(lines):
            line.journal_entry_id = self.id
            line.line_index = index
            self.lines.append(line)
        self.updated_at = _utcnow()

    # ── totals ────────────────────────────────────────────────────────────
    def total_debits(self) -> Money:
        """Total de débitos en moneda de la operación (líneas normales)."""
        total = Money.zero(self.currency_code)
        for line in self.lines:
            total = total.add(line.debit)
        return total

    def total_credits(self) -> Money:
        total = Money.zero(self.currency_code)
        for line in self.lines:
            total = total.add(line.credit)
        return total

    def base_total_debits(self) -> Money:
        total = Money.zero(self.base_currency_code)
        for line in self.lines:
            total = total.add(line.base_debit)
        return total

    def base_total_credits(self) -> Money:
        total = Money.zero(self.base_currency_code)
        for line in self.lines:
            total = total.add(line.base_credit)
        return total

    def is_balanced(self) -> bool:
        return (self.total_debits().amount == self.total_credits().amount
                and self.base_total_debits().amount == self.base_total_credits().amount)

    # ── lifecycle ─────────────────────────────────────────────────────────
    def validate(self, by: str | None = None) -> None:
        """DRAFT → VALIDATED. Enforces line integrity and double-entry balance."""
        if self.status in (JournalEntryStatus.POSTED, JournalEntryStatus.REVERSED):
            raise JournalEntryAlreadyPostedError(
                f"El asiento {self.entry_number} ya está contabilizado")
        if self.status is not JournalEntryStatus.DRAFT:
            raise InvalidEntryStateError(
                f"No se valida un asiento en estado {self.status.value}")
        if len(self.lines) < 2:
            raise EmptyEntryError("Un asiento requiere al menos dos líneas")
        for line in self.lines:
            line.validate()
            if line.line_role is LineRole.NORMAL and line.currency_code != self.currency_code:
                raise EmptyEntryError(
                    f"Todas las líneas van en la moneda del asiento ({self.currency_code})")
            if line.base_debit.currency_code != self.base_currency_code:
                raise EmptyEntryError("Importe base en otra moneda que la base del asiento")
        if not self.is_balanced():
            raise UnbalancedJournalEntryError(
                f"El asiento {self.entry_number} no cuadra: débitos "
                f"{self.base_total_debits().to_string()} ≠ créditos "
                f"{self.base_total_credits().to_string()}")
        self.status = JournalEntryStatus.VALIDATED
        self.validated_by = by
        self.validated_at = _utcnow()
        self.updated_at = self.validated_at

    def mark_posted(self, by: str | None = None) -> None:
        """VALIDATED → POSTED. Period control is enforced by the posting service."""
        if self.status in (JournalEntryStatus.POSTED, JournalEntryStatus.REVERSED):
            raise JournalEntryAlreadyPostedError(
                f"El asiento {self.entry_number} ya está contabilizado")
        if self.status is not JournalEntryStatus.VALIDATED:
            raise InvalidEntryStateError(
                f"Sólo se contabiliza un asiento validado (está {self.status.value})")
        if not self.is_balanced():
            raise UnbalancedJournalEntryError(
                f"El asiento {self.entry_number} se desbalanceó antes de contabilizar")
        self.status = JournalEntryStatus.POSTED
        self.posted_at = _utcnow()
        self.posted_by = by or self.created_by
        self.updated_at = self.posted_at

    def mark_reversed(self, reversal_entry_id: str) -> None:
        """POSTED → REVERSED. The original entry is never edited or deleted."""
        if self.status is not JournalEntryStatus.POSTED:
            raise InvalidEntryStateError(
                f"Sólo se revierte un asiento contabilizado (está {self.status.value})")
        self.status = JournalEntryStatus.REVERSED
        self.reversed_by_entry_id = reversal_entry_id
        self.updated_at = _utcnow()

    def cancel(self, by: str | None = None, reason: str | None = None) -> None:
        """DRAFT/VALIDATED → CANCELLED. Published entries can never be cancelled."""
        if self.status not in (JournalEntryStatus.DRAFT, JournalEntryStatus.VALIDATED):
            raise JournalEntryImmutableError(
                f"El asiento {self.entry_number} está {self.status.value}; "
                "corríjalo con un reverso")
        self.status = JournalEntryStatus.CANCELLED
        self.cancelled_by = by
        self.cancel_reason = (reason or "").strip() or None
        self.updated_at = _utcnow()

    def return_to_draft(self) -> None:
        """VALIDATED → DRAFT para corregir líneas antes de contabilizar."""
        if self.status is not JournalEntryStatus.VALIDATED:
            raise InvalidEntryStateError(
                f"Sólo un asiento validado vuelve a borrador (está {self.status.value})")
        self.status = JournalEntryStatus.DRAFT
        self.validated_by = None
        self.validated_at = None
        self.updated_at = _utcnow()

    # ── guards ────────────────────────────────────────────────────────────
    def _assert_mutable(self) -> None:
        if self.status is not JournalEntryStatus.DRAFT:
            raise JournalEntryImmutableError(
                f"El asiento {self.entry_number} está {self.status.value} y no se modifica; "
                "las correcciones exigen un asiento de reverso")
