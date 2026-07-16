"""Budget use cases — versioned budgets with blocking availability control."""

from __future__ import annotations

import json
from datetime import date

from backend.domain.finance.entities.budget import Budget
from backend.domain.finance.exceptions import BudgetControlError, FinanceDomainError
from backend.domain.finance.services.budget_service import BudgetDomainService
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class CreateBudgetUseCase:
    def execute(self, connection, *, name: str, fiscal_year: int,
                lines: list[dict], branch_id: str | None = None,
                version: int = 1, operation_id: str) -> Budget:
        """``lines``: [{"account_id", "period_code", "planned_amount",
        "currency_code"?, "cost_center_id"?}]"""
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.budgets.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            budget = Budget.create(name, fiscal_year, operation_id,
                                   version=version, branch_id=branch_id)
            for line in lines:
                account_id = str(line["account_id"])
                if uow.accounts.get(account_id) is None:
                    raise FinanceDomainError(f"La cuenta {account_id} no existe")
                budget.add_line(
                    account_id, str(line["period_code"]),
                    Money.from_string(str(line["planned_amount"]),
                                      str(line.get("currency_code") or "MXN")),
                    cost_center_id=line.get("cost_center_id"),
                    branch_id=line.get("branch_id"),
                )
            uow.budgets.save(budget)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.BUDGET_CREATED.value,
                payload_json=json.dumps({"budget_id": budget.id, "name": name,
                                         "fiscal_year": fiscal_year}),
                operation_id=operation_id,
            )
            return budget


class SubmitBudgetUseCase:
    def execute(self, connection, *, budget_id: str, submitted_by: str) -> Budget:
        with FinanceUnitOfWork(connection) as uow:
            budget = uow.budgets.get(budget_id)
            if budget is None:
                raise FinanceDomainError("El presupuesto no existe")
            budget.submit(submitted_by)
            uow.budgets.update(budget)
            return budget


class ApproveBudgetUseCase:
    def execute(self, connection, *, budget_id: str, approved_by: str,
                operation_id: str) -> Budget:
        with FinanceUnitOfWork(connection) as uow:
            budget = uow.budgets.get(budget_id)
            if budget is None:
                raise FinanceDomainError("El presupuesto no existe")
            budget.approve(approved_by)
            uow.budgets.update(budget)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.BUDGET_APPROVED.value,
                payload_json=json.dumps({"budget_id": budget.id,
                                         "approved_by": approved_by}),
                operation_id=operation_id,
            )
            return budget


class RegisterExpenseRequestUseCase:
    """Commits budget availability for an expense request (blocking control).
    Accrual happens later when the actual expense posts."""

    def __init__(self) -> None:
        self._domain = BudgetDomainService()

    def execute(self, connection, *, account_id: str, amount: str, request_date: date,
                cost_center_id: str | None = None, branch_id: str | None = None,
                currency_code: str = "MXN", operation_id: str) -> str:
        period_code = f"{request_date.year:04d}-{request_date.month:02d}"
        money = Money.from_string(amount, currency_code)
        try:
            with FinanceUnitOfWork(connection) as uow:
                budget = uow.budgets.find_approved_for_year(request_date.year, branch_id)
                if budget is None:
                    raise BudgetControlError(
                        f"No hay presupuesto aprobado para {request_date.year}"
                    )
                self._domain.commit(budget, account_id, period_code, money,
                                    cost_center_id=cost_center_id)
                uow.budgets.update(budget)
                uow.outbox.enqueue(
                    event_id=new_uuid(), event_name=EventName.BUDGET_COMMITTED.value,
                    payload_json=json.dumps({
                        "budget_id": budget.id, "account_id": account_id,
                        "period_code": period_code, "amount": money.to_string(),
                    }),
                    operation_id=operation_id,
                )
                return budget.id
        except BudgetControlError:
            # The failed commitment rolled back; the exceeded alert must survive
            # in its own transaction so control can act on it.
            with FinanceUnitOfWork(connection) as uow:
                uow.outbox.enqueue(
                    event_id=new_uuid(), event_name=EventName.BUDGET_EXCEEDED.value,
                    payload_json=json.dumps({
                        "account_id": account_id, "period_code": period_code,
                        "amount": money.to_string(),
                    }),
                    operation_id=operation_id,
                )
            raise
