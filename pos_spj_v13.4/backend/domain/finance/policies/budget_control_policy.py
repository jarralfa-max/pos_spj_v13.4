"""Budget control policy — availability checks for commitments and accruals."""

from __future__ import annotations

from backend.domain.finance.entities.budget import Budget, BudgetLine
from backend.domain.finance.enums import BudgetStatus
from backend.domain.finance.exceptions import BudgetControlError
from backend.domain.finance.value_objects.money import Money


class BudgetControlPolicy:
    """Blocking control: spending against an approved budget must not exceed availability."""

    def enforce_budget_approved(self, budget: Budget) -> None:
        if budget.status is not BudgetStatus.APPROVED:
            raise BudgetControlError(
                f"Budget {budget.name!r} is {budget.status.value}; only APPROVED budgets control spending"
            )

    def enforce_availability(self, line: BudgetLine, amount: Money) -> None:
        available = line.available()
        if amount > available:
            raise BudgetControlError(
                f"Amount {amount.to_string()} exceeds budget availability {available.to_string()} "
                f"for account {line.account_id} in period {line.period_code}"
            )
