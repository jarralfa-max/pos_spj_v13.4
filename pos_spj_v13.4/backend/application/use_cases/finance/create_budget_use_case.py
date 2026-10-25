"""Presupuestos versionados (§16): crear y crear una nueva versión.

Una versión aprobada no se edita: la corrección es una VERSIÓN nueva (borrador)
que copia las partidas y referencia a la anterior; al aprobarse y activarse
pasa a controlar el gasto (la consulta toma la versión vigente más alta).
"""

from __future__ import annotations

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.budget import Budget
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import AccountNotFoundError, FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName

_DIMENSIONS = ("cost_center_id", "branch_id", "profit_center_id", "project_id", "department_id")


class CreateBudgetUseCase:
    def execute(self, connection, *, name: str, fiscal_year: int, lines: list[dict],
                operation_id: str, branch_id: str | None = None, blocking: bool = True,
                created_by: str | None = None) -> Budget:
        """``lines``: [{"account_id", "period_code", "planned_amount",
        "currency_code"?, "cost_center_id"?, "project_id"?, "department_id"?,
        "profit_center_id"?, "branch_id"?}]"""
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.budgets.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            version = uow.budgets.next_version(name.strip(), fiscal_year)
            if version != 1:
                raise FinanceDomainError(
                    f"Ya existe el presupuesto {name!r} {fiscal_year}; cree una nueva versión")
            budget = Budget.create(name, fiscal_year, operation_id, version=1,
                                   branch_id=branch_id, blocking=blocking)
            _add_lines(uow, budget, lines)
            uow.budgets.save(budget)
            _record(uow, budget, operation_id, created_by)
            return budget


class CreateBudgetVersionUseCase:
    def execute(self, connection, *, budget_id: str, operation_id: str,
                created_by: str | None = None, lines: list[dict] | None = None) -> Budget:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.budgets.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            previous = uow.budgets.get(budget_id)
            if previous is None:
                raise FinanceDomainError("El presupuesto no existe")
            budget = Budget.create(previous.name, previous.fiscal_year, operation_id,
                                   version=uow.budgets.next_version(previous.name,
                                                                    previous.fiscal_year),
                                   branch_id=previous.branch_id, blocking=previous.blocking,
                                   previous_version_id=previous.id)
            source = lines if lines is not None else [
                {"account_id": l.account_id, "period_code": l.period_code,
                 "planned_amount": l.planned_amount.to_string(),
                 "currency_code": l.planned_amount.currency_code,
                 **{d: getattr(l, d) for d in _DIMENSIONS}} for l in previous.lines]
            _add_lines(uow, budget, source)
            uow.budgets.save(budget)
            _record(uow, budget, operation_id, created_by)
            return budget


def _add_lines(uow: FinanceUnitOfWork, budget: Budget, lines: list[dict]) -> None:
    for line in lines:
        account_id = str(line["account_id"])
        if uow.accounts.get(account_id) is None:
            raise AccountNotFoundError(f"La cuenta {account_id} no existe")
        budget.add_line(account_id, str(line["period_code"]),
                        Money.from_string(str(line["planned_amount"]),
                                          str(line.get("currency_code") or "MXN")),
                        **{d: line.get(d) or None for d in _DIMENSIONS})


def _record(uow: FinanceUnitOfWork, budget: Budget, operation_id: str,
            created_by: str | None) -> None:
    uow.audit(AuditAction.BUDGET_CHANGED, entity_type="budget", entity_id=budget.id,
              operation_id=operation_id, user_id=created_by,
              after={"name": budget.name, "fiscal_year": budget.fiscal_year,
                     "version": budget.version, "lines": len(budget.lines),
                     "blocking": budget.blocking}, branch_id=budget.branch_id)
    publish_finance_event(uow, EventName.BUDGET_CREATED, {
        "budget_id": budget.id, "name": budget.name, "fiscal_year": budget.fiscal_year,
        "version": budget.version,
    }, operation_id=operation_id, entity_id=budget.id, branch_id=budget.branch_id)
