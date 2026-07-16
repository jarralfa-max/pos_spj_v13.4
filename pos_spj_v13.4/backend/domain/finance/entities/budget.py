"""Budget entities — approved spending plans with commitment/accrual control."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import BudgetStatus
from backend.domain.finance.exceptions import BudgetControlError, FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class BudgetLine:
    id: str
    budget_id: str
    account_id: str
    period_code: str            # "YYYY-MM"
    planned_amount: Money
    committed_amount: Money
    accrued_amount: Money
    cost_center_id: str | None = None
    branch_id: str | None = None

    @classmethod
    def create(cls, budget_id: str, account_id: str, period_code: str, planned_amount: Money,
               *, cost_center_id: str | None = None, branch_id: str | None = None) -> "BudgetLine":
        if planned_amount.is_negative():
            raise FinanceDomainError("Budget planned amount must not be negative")
        zero = Money.zero(planned_amount.currency_code)
        return cls(
            id=new_uuid(), budget_id=budget_id, account_id=account_id,
            period_code=period_code, planned_amount=planned_amount,
            committed_amount=zero, accrued_amount=zero,
            cost_center_id=cost_center_id, branch_id=branch_id,
        )

    def available(self) -> Money:
        return self.planned_amount.subtract(self.committed_amount).subtract(self.accrued_amount)

    def commit(self, amount: Money, *, blocking: bool = True) -> None:
        if not amount.is_positive():
            raise FinanceDomainError("Commitment amount must be positive")
        if blocking and amount > self.available():
            raise BudgetControlError(
                f"Commitment {amount.to_string()} exceeds available budget {self.available().to_string()}"
            )
        self.committed_amount = self.committed_amount.add(amount)

    def release_commitment(self, amount: Money) -> None:
        if amount > self.committed_amount:
            raise BudgetControlError("Cannot release more than the committed amount")
        self.committed_amount = self.committed_amount.subtract(amount)

    def accrue(self, amount: Money, *, from_commitment: bool = True, blocking: bool = True) -> None:
        if not amount.is_positive():
            raise FinanceDomainError("Accrual amount must be positive")
        if from_commitment:
            release = amount if amount <= self.committed_amount else self.committed_amount
            self.committed_amount = self.committed_amount.subtract(release)
        elif blocking and amount > self.available():
            raise BudgetControlError(
                f"Accrual {amount.to_string()} exceeds available budget {self.available().to_string()}"
            )
        self.accrued_amount = self.accrued_amount.add(amount)


@dataclass(slots=True)
class Budget:
    id: str
    name: str
    fiscal_year: int
    version: int
    operation_id: str
    status: BudgetStatus = BudgetStatus.DRAFT
    approved_by: str | None = None
    approved_at: str | None = None
    submitted_by: str | None = None
    branch_id: str | None = None
    lines: list[BudgetLine] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, name: str, fiscal_year: int, operation_id: str, *,
               version: int = 1, branch_id: str | None = None) -> "Budget":
        if not name or not name.strip():
            raise FinanceDomainError("Budget.name is required")
        return cls(
            id=new_uuid(), name=name.strip(), fiscal_year=fiscal_year,
            version=version, operation_id=operation_id, branch_id=branch_id,
        )

    def add_line(self, account_id: str, period_code: str, planned_amount: Money, **kwargs) -> BudgetLine:
        if self.status not in (BudgetStatus.DRAFT,):
            raise FinanceDomainError(f"Cannot modify budget in status {self.status.value}")
        line = BudgetLine.create(self.id, account_id, period_code, planned_amount, **kwargs)
        self.lines.append(line)
        return line

    def submit(self, submitted_by: str) -> None:
        if self.status is not BudgetStatus.DRAFT:
            raise FinanceDomainError(f"Cannot submit budget in status {self.status.value}")
        if not self.lines:
            raise FinanceDomainError("Cannot submit an empty budget")
        self.status = BudgetStatus.SUBMITTED
        self.submitted_by = submitted_by
        self.updated_at = _utcnow()

    def approve(self, approved_by: str) -> None:
        if self.status is not BudgetStatus.SUBMITTED:
            raise FinanceDomainError(f"Cannot approve budget in status {self.status.value}")
        if self.submitted_by and approved_by == self.submitted_by:
            raise FinanceDomainError("Segregation of duties: submitter cannot approve their own budget")
        self.status = BudgetStatus.APPROVED
        self.approved_by = approved_by
        self.approved_at = _utcnow()
        self.updated_at = self.approved_at

    def reject(self) -> None:
        if self.status is not BudgetStatus.SUBMITTED:
            raise FinanceDomainError(f"Cannot reject budget in status {self.status.value}")
        self.status = BudgetStatus.REJECTED
        self.updated_at = _utcnow()

    def close(self) -> None:
        if self.status is not BudgetStatus.APPROVED:
            raise FinanceDomainError(f"Cannot close budget in status {self.status.value}")
        self.status = BudgetStatus.CLOSED
        self.updated_at = _utcnow()
