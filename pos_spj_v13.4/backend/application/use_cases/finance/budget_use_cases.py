"""Budget use cases — versioned budgets with blocking availability control."""

from __future__ import annotations

import json
from datetime import date

from backend.domain.finance.entities.budget import Budget
from backend.domain.finance.exceptions import (
    BudgetControlError,
    FinanceDomainError,
    IdempotencyConflictError,
)
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

    Auditoría F15: la solicitud queda registrada (``expense_requests``) con su
    identidad; la idempotencia se verifica ANTES de comprometer, así que
    repetir la misma operación no vuelve a restar disponible ni emite otro
    evento. Devuelve el id de la SOLICITUD (antes devolvía el del presupuesto
    y la solicitud no existía). Su ciclo sigue en ``ResolveExpenseRequestUseCase``:
    devengar contra un documento o liberar al cancelarse."""

    def __init__(self) -> None:
        self._domain = BudgetDomainService()

    def execute(self, connection, *, account_id: str, amount: str, request_date: date,
                cost_center_id: str | None = None, branch_id: str | None = None,
                currency_code: str = "MXN", operation_id: str,
                requested_by: str | None = None) -> str:
        period_code = f"{request_date.year:04d}-{request_date.month:02d}"
        money = Money.from_string(amount, currency_code)
        try:
            with FinanceUnitOfWork(connection) as uow:
                previous = uow.expense_requests.find_by_operation_id(operation_id)
                if previous is not None:
                    if (previous["account_id"] != account_id
                            or Money.from_string(previous["amount"],
                                                 previous["currency_code"]).amount != money.amount):
                        raise IdempotencyConflictError(
                            f"La operación {operation_id} ya registró otra solicitud de gasto")
                    return previous["id"]
                budget = uow.budgets.find_approved_for_year(request_date.year, branch_id)
                if budget is None:
                    raise BudgetControlError(
                        f"No hay presupuesto aprobado para {request_date.year}"
                    )
                self._domain.commit(budget, account_id, period_code, money,
                                    cost_center_id=cost_center_id)
                uow.budgets.update(budget)
                request_id = uow.expense_requests.add(
                    budget_id=budget.id, account_id=account_id, period_code=period_code,
                    cost_center_id=cost_center_id, branch_id=branch_id,
                    amount=money.to_string(), currency_code=money.currency_code,
                    requested_by=requested_by, operation_id=operation_id)
                uow.outbox.enqueue(
                    event_id=new_uuid(), event_name=EventName.BUDGET_COMMITTED.value,
                    payload_json=json.dumps({
                        "budget_id": budget.id, "expense_request_id": request_id,
                        "account_id": account_id, "period_code": period_code,
                        "amount": money.to_string(),
                    }),
                    operation_id=operation_id,
                )
                return request_id
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


class ResolveExpenseRequestUseCase:
    """Cierra el ciclo de una solicitud comprometida (auditoría F15).

    - ``accrue``: el gasto se materializó en un documento (factura, CxP): el
      compromiso pasa a devengado por el mismo importe, sin duplicarse.
    - ``release``: la solicitud se canceló: el compromiso se libera.
    Ambos son de una sola vez: una solicitud ya resuelta no se resuelve otra vez.
    """

    def __init__(self) -> None:
        self._domain = BudgetDomainService()

    def accrue(self, connection, *, expense_request_id: str, document_reference: str,
               resolved_by: str | None = None) -> None:
        if not (document_reference or "").strip():
            raise FinanceDomainError("Devengar exige el documento que lo sustenta")
        self._resolve(connection, expense_request_id, status="ACCRUED",
                      resolved_by=resolved_by, reference=document_reference.strip(),
                      reason=None)

    def release(self, connection, *, expense_request_id: str, reason: str,
                resolved_by: str | None = None) -> None:
        if not (reason or "").strip():
            raise FinanceDomainError("Liberar un compromiso exige el motivo")
        self._resolve(connection, expense_request_id, status="RELEASED",
                      resolved_by=resolved_by, reference=None, reason=reason.strip())

    def _resolve(self, connection, request_id: str, *, status: str, resolved_by,
                 reference, reason) -> None:
        with FinanceUnitOfWork(connection) as uow:
            request = uow.expense_requests.get(request_id)
            if request is None:
                raise FinanceDomainError("La solicitud de gasto no existe")
            if request["status"] != "COMMITTED":
                raise FinanceDomainError(
                    f"La solicitud ya está {request['status'].lower()}; no se resuelve otra vez")
            budget = uow.budgets.get(request["budget_id"])
            money = Money.from_string(request["amount"], request["currency_code"])
            line = self._domain.find_line(budget, request["account_id"], request["period_code"],
                                          cost_center_id=request["cost_center_id"])
            if line is None:
                raise BudgetControlError("La línea presupuestal de la solicitud ya no existe")
            if status == "ACCRUED":
                line.accrue(money, from_commitment=True)
                event = EventName.BUDGET_ACCRUED
            else:
                line.release_commitment(money)
                event = EventName.BUDGET_COMMITMENT_RELEASED
            uow.budgets.update(budget)
            uow.expense_requests.resolve(request_id, status=status, resolved_by=resolved_by,
                                         reference=reference, reason=reason)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=event.value,
                payload_json=json.dumps({
                    "budget_id": budget.id, "expense_request_id": request_id,
                    "amount": money.to_string(), "document_reference": reference,
                    "reason": reason,
                }),
                operation_id=new_uuid(),
            )
