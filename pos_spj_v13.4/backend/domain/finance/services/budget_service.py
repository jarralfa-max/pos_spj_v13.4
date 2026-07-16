"""BudgetDomainService — budget lifecycle plus commitment/accrual control."""

from __future__ import annotations

from backend.domain.finance.entities.budget import Budget, BudgetLine
from backend.domain.finance.exceptions import BudgetControlError
from backend.domain.finance.policies.budget_control_policy import BudgetControlPolicy
from backend.domain.finance.value_objects.money import Money


class BudgetDomainService:
    def __init__(self) -> None:
        self._policy = BudgetControlPolicy()

    @staticmethod
    def find_line(budget: Budget, account_id: str, period_code: str,
                  *, cost_center_id: str | None = None) -> BudgetLine | None:
        for line in budget.lines:
            if (line.account_id == account_id and line.period_code == period_code
                    and line.cost_center_id == cost_center_id):
                return line
        return None

    def commit(self, budget: Budget, account_id: str, period_code: str, amount: Money,
               *, cost_center_id: str | None = None, blocking: bool = True) -> BudgetLine:
        self._policy.enforce_budget_approved(budget)
        line = self.find_line(budget, account_id, period_code, cost_center_id=cost_center_id)
        if line is None:
            raise BudgetControlError(
                f"No budget line for account {account_id} in period {period_code}"
            )
        if blocking:
            self._policy.enforce_availability(line, amount)
        line.commit(amount, blocking=blocking)
        return line

    def accrue(self, budget: Budget, account_id: str, period_code: str, amount: Money,
               *, cost_center_id: str | None = None, from_commitment: bool = True,
               blocking: bool = True) -> BudgetLine:
        self._policy.enforce_budget_approved(budget)
        line = self.find_line(budget, account_id, period_code, cost_center_id=cost_center_id)
        if line is None:
            raise BudgetControlError(
                f"No budget line for account {account_id} in period {period_code}"
            )
        line.accrue(amount, from_commitment=from_commitment, blocking=blocking)
        return line
