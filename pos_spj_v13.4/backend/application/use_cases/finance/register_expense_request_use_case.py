"""RegisterExpenseRequestUseCase — solicitud de gasto (§16).

La solicitud nace REQUESTED con el número de aprobaciones que fije la regla
vigente (importe, sucursal, categoría, centro de costo, solicitante). Se valida
contra el presupuesto que controla el gasto: si ya no cabe en un presupuesto
bloqueante, se rechaza desde la captura (y queda la alerta BUDGET_EXCEEDED);
el compromiso real ocurre al quedar APROBADA. Idempotente por ``operation_id``.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.application.use_cases.finance._support import period_code as to_period
from backend.application.use_cases.finance.commit_budget_use_case import controlling_budget
from backend.domain.finance.entities.expense import ExpenseApprovalPolicy, ExpenseRequest
from backend.domain.finance.enums import AuditAction, BudgetControlLevel
from backend.domain.finance.exceptions import (
    AccountNotFoundError,
    BudgetControlError,
    BudgetExceededError,
    IdempotencyConflictError,
)
from backend.domain.finance.policies.budget_control_policy import BudgetControlPolicy
from backend.domain.finance.services.budget_service import BudgetDomainService
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class RegisterExpenseRequestUseCase:
    def execute(self, connection, *, account_id: str, amount: str, request_date: date,
                operation_id: str, requested_by: str, currency_code: str = "MXN",
                category: str = "", description: str = "", cost_center_id: str | None = None,
                project_id: str | None = None, department_id: str | None = None,
                branch_id: str | None = None, supplier_id: str | None = None) -> str:
        money = Money.from_string(amount, currency_code)
        period = to_period(request_date)
        dims = {"cost_center_id": cost_center_id, "project_id": project_id,
                "department_id": department_id}
        try:
            with FinanceUnitOfWork(connection) as uow:
                previous = uow.expense_requests.find_by_operation_id(operation_id)
                if previous is not None:
                    if previous.account_id != account_id or previous.amount.amount != money.amount:
                        raise IdempotencyConflictError(
                            f"La operación {operation_id} ya registró otra solicitud de gasto")
                    return previous.id
                if uow.accounts.get(account_id) is None:
                    raise AccountNotFoundError("La cuenta del gasto no existe")
                budget = controlling_budget(uow, request_date.year, branch_id)
                line = BudgetDomainService.find_line(budget, account_id, period, **dims)
                if line is None:
                    raise BudgetControlError(
                        f"El presupuesto {budget.name!r} no tiene partida para esa cuenta en "
                        f"{period}")
                level = BudgetControlPolicy(uow.settings.budget_warning_percent).evaluate(
                    line, money)
                if level is BudgetControlLevel.BLOCKING and budget.blocking:
                    raise BudgetExceededError(
                        f"La solicitud de {money.to_string()} excede lo disponible "
                        f"({line.available().to_string()}); requiere autorización de exceso "
                        "al aprobarse")
                required = ExpenseApprovalPolicy.required_approvals(
                    uow.expense_requests.active_rules(), amount=money, branch_id=branch_id,
                    category=category, cost_center_id=cost_center_id,
                    requester_id=requested_by)
                request = ExpenseRequest.create(
                    account_id=account_id, period_code=period, amount=money,
                    requested_by=requested_by, operation_id=operation_id,
                    required_approvals=required, budget_id=budget.id, category=category,
                    description=description, branch_id=branch_id, supplier_id=supplier_id,
                    **dims)
                uow.expense_requests.save(request)
                uow.audit(AuditAction.EXPENSE_DECIDED, entity_type="expense_request",
                          entity_id=request.id, operation_id=operation_id,
                          user_id=requested_by,
                          after={"status": request.status.value, "amount": money.to_string(),
                                 "required_approvals": required,
                                 "control_level": level.value}, branch_id=branch_id)
                publish_finance_event(uow, EventName.EXPENSE_REQUESTED, {
                    "expense_request_id": request.id, "amount": money.to_string(),
                    "account_id": account_id, "required_approvals": required,
                    "control_level": level.value,
                }, operation_id=operation_id, entity_id=request.id, branch_id=branch_id)
                return request.id
        except BudgetExceededError:
            # La alerta de exceso sobrevive en su propia transacción.
            with FinanceUnitOfWork(connection) as uow:
                publish_finance_event(uow, EventName.BUDGET_EXCEEDED, {
                    "account_id": account_id, "period_code": period,
                    "amount": money.to_string(), "authorized": False,
                }, operation_id=operation_id, entity_id=operation_id, branch_id=branch_id)
            raise
