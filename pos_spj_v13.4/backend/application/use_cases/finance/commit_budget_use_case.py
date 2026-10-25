"""CommitBudgetUseCase — compromete presupuesto dentro de la transacción de quien llama (§16).

Evalúa AVAILABLE / WARNING / BLOCKING con el umbral de advertencia
configurado. En un presupuesto bloqueante, exceder lo aprobado exige
autorización de exceso; si se autoriza (o el presupuesto sólo advierte), el
exceso queda registrado y se publica BUDGET_EXCEEDED.
"""

from __future__ import annotations

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.budget import Budget
from backend.domain.finance.enums import BudgetControlLevel
from backend.domain.finance.exceptions import BudgetNotApprovedError
from backend.domain.finance.services.budget_service import BudgetDomainService
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


def controlling_budget(uow: FinanceUnitOfWork, year: int, branch_id: str | None) -> Budget:
    budget = uow.budgets.find_approved_for_year(year, branch_id)
    if budget is None:
        raise BudgetNotApprovedError(f"No hay presupuesto aprobado o activo para {year}")
    return budget


class CommitBudgetUseCase:
    def commit_in(self, uow: FinanceUnitOfWork, budget: Budget, *, account_id: str,
                  period_code: str, amount: Money, operation_id: str, entity_id: str,
                  excess_authorized: bool = False, **dims) -> BudgetControlLevel:
        service = BudgetDomainService(uow.settings.budget_warning_percent)
        _, level = service.commit(budget, account_id, period_code, amount,
                                  excess_authorized=excess_authorized, **dims)
        uow.budgets.update(budget)
        publish_finance_event(uow, EventName.BUDGET_COMMITTED, {
            "budget_id": budget.id, "account_id": account_id, "period_code": period_code,
            "amount": amount.to_string(), "control_level": level.value,
            "expense_request_id": entity_id,
        }, operation_id=operation_id, entity_id=entity_id, branch_id=budget.branch_id)
        if level is BudgetControlLevel.BLOCKING:
            publish_finance_event(uow, EventName.BUDGET_EXCEEDED, {
                "budget_id": budget.id, "account_id": account_id, "period_code": period_code,
                "amount": amount.to_string(), "authorized": excess_authorized,
                "expense_request_id": entity_id,
            }, operation_id=operation_id, entity_id=entity_id, branch_id=budget.branch_id)
        return level
