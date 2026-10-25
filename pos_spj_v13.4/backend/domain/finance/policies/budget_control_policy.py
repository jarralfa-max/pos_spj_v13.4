"""Budget control policy (§16): AVAILABLE / WARNING / BLOCKING.

- AVAILABLE: tras el gasto, el consumo queda por debajo del umbral de advertencia.
- WARNING: supera el umbral configurado pero no lo aprobado.
- BLOCKING: excede lo aprobado. En un presupuesto bloqueante se rechaza salvo
  exceso autorizado expresamente (permiso propio + motivo).
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.finance.entities.budget import Budget, BudgetLine
from backend.domain.finance.enums import BudgetControlLevel
from backend.domain.finance.exceptions import BudgetExceededError, BudgetNotApprovedError
from backend.domain.finance.value_objects.money import Money


class BudgetControlPolicy:
    def __init__(self, warning_percent: Decimal | None = None) -> None:
        self._warning_percent = warning_percent

    def enforce_budget_approved(self, budget: Budget) -> None:
        if not budget.controls_spending:
            raise BudgetNotApprovedError(
                f"El presupuesto {budget.name!r} está {budget.status.value}; sólo uno aprobado "
                "o activo controla el gasto")

    def evaluate(self, line: BudgetLine, amount: Money) -> BudgetControlLevel:
        after = line.consumed().add(amount)
        if after > line.planned_amount:
            return BudgetControlLevel.BLOCKING
        if self._warning_percent is not None and line.planned_amount.is_positive():
            ratio = after.amount * Decimal("100") / line.planned_amount.amount
            if ratio >= self._warning_percent:
                return BudgetControlLevel.WARNING
        return BudgetControlLevel.AVAILABLE

    def enforce(self, budget: Budget, line: BudgetLine, amount: Money, *,
                excess_authorized: bool = False) -> BudgetControlLevel:
        self.enforce_budget_approved(budget)
        level = self.evaluate(line, amount)
        if level is BudgetControlLevel.BLOCKING and budget.blocking and not excess_authorized:
            raise BudgetExceededError(
                f"El gasto de {amount.to_string()} excede lo disponible "
                f"({line.available().to_string()}) en la partida {line.period_code}; "
                "requiere autorización de exceso")
        return level
