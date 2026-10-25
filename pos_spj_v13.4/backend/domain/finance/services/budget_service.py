"""BudgetDomainService — commitment / accrual / payment against approved budgets."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.finance.entities.budget import Budget, BudgetLine
from backend.domain.finance.enums import BudgetControlLevel
from backend.domain.finance.exceptions import BudgetControlError
from backend.domain.finance.policies.budget_control_policy import BudgetControlPolicy
from backend.domain.finance.value_objects.money import Money


class BudgetDomainService:
    def __init__(self, warning_percent: Decimal | None = None) -> None:
        self._policy = BudgetControlPolicy(warning_percent)

    @staticmethod
    def find_line(budget: Budget, account_id: str, period_code: str, *,
                  cost_center_id: str | None = None, project_id: str | None = None,
                  department_id: str | None = None,
                  profit_center_id: str | None = None) -> BudgetLine | None:
        for line in budget.lines:
            if line.matches(account_id=account_id, period_code=period_code,
                            cost_center_id=cost_center_id, project_id=project_id,
                            department_id=department_id, profit_center_id=profit_center_id):
                return line
        return None

    def _line(self, budget: Budget, account_id: str, period_code: str, **dims) -> BudgetLine:
        line = self.find_line(budget, account_id, period_code, **dims)
        if line is None:
            raise BudgetControlError(
                f"El presupuesto {budget.name!r} no tiene partida para esa cuenta en {period_code}")
        return line

    def commit(self, budget: Budget, account_id: str, period_code: str, amount: Money, *,
               excess_authorized: bool = False, **dims) -> tuple[BudgetLine, BudgetControlLevel]:
        line = self._line(budget, account_id, period_code, **dims)
        level = self._policy.enforce(budget, line, amount, excess_authorized=excess_authorized)
        line.commit(amount)
        return line, level

    def accrue(self, budget: Budget, account_id: str, period_code: str, amount: Money, *,
               from_commitment: Money | None = None, excess_authorized: bool = False,
               **dims) -> tuple[BudgetLine, BudgetControlLevel]:
        line = self._line(budget, account_id, period_code, **dims)
        extra = amount.subtract(from_commitment) if from_commitment is not None else amount
        level = BudgetControlLevel.AVAILABLE
        if extra.is_positive():
            level = self._policy.enforce(budget, line, extra, excess_authorized=excess_authorized)
        else:
            self._policy.enforce_budget_approved(budget)
        line.accrue(amount, from_commitment=from_commitment)
        return line, level

    def pay(self, budget: Budget, account_id: str, period_code: str, amount: Money,
            **dims) -> BudgetLine:
        line = self._line(budget, account_id, period_code, **dims)
        line.pay(amount)
        return line

    def release(self, budget: Budget, account_id: str, period_code: str, amount: Money,
                **dims) -> BudgetLine:
        line = self._line(budget, account_id, period_code, **dims)
        line.release_commitment(amount)
        return line
