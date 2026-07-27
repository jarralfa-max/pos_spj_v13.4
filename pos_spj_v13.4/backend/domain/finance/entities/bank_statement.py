"""BankStatement entities — imported statements for reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class BankStatementLine:
    id: str
    bank_statement_id: str
    transaction_date: date
    description: str
    amount: Money            # positive = inflow, negative = outflow
    external_reference: str = ""
    matched_journal_line_id: str | None = None
    reconciled: bool = False
    line_index: int = 0

    @classmethod
    def create(cls, bank_statement_id: str, transaction_date: date, description: str,
               amount: Money, *, external_reference: str = "", line_index: int = 0) -> "BankStatementLine":
        return cls(
            id=new_uuid(), bank_statement_id=bank_statement_id,
            transaction_date=transaction_date, description=description,
            amount=amount, external_reference=external_reference, line_index=line_index,
        )


@dataclass(slots=True)
class BankStatement:
    id: str
    treasury_account_id: str
    statement_date: date
    opening_balance: Money
    closing_balance: Money
    operation_id: str
    imported_at: str = field(default_factory=_utcnow)
    lines: list[BankStatementLine] = field(default_factory=list)

    @classmethod
    def create(cls, treasury_account_id: str, statement_date: date,
               opening_balance: Money, closing_balance: Money, operation_id: str) -> "BankStatement":
        if not treasury_account_id:
            raise FinanceDomainError("BankStatement requires a treasury_account_id")
        return cls(
            id=new_uuid(), treasury_account_id=treasury_account_id,
            statement_date=statement_date, opening_balance=opening_balance,
            closing_balance=closing_balance, operation_id=operation_id,
        )

    def add_line(self, transaction_date: date, description: str, amount: Money,
                 external_reference: str = "") -> BankStatementLine:
        line = BankStatementLine.create(
            self.id, transaction_date, description, amount,
            external_reference=external_reference, line_index=len(self.lines),
        )
        self.lines.append(line)
        return line

    def movement_total(self) -> Money:
        total = Money.zero(self.opening_balance.currency_code)
        for line in self.lines:
            total = total.add(line.amount)
        return total

    def is_internally_consistent(self) -> bool:
        return self.opening_balance.add(self.movement_total()).amount == self.closing_balance.amount
