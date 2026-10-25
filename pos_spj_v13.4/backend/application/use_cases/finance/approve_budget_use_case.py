"""Flujo del presupuesto (§16): enviar, aprobar, rechazar, activar, cerrar, cancelar.

Quien envía no aprueba. Rechazar devuelve a borrador con motivo; cancelar sólo
procede sin compromisos ni gasto; un presupuesto activo se cierra al terminar.
"""

from __future__ import annotations

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.budget import Budget
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class BudgetWorkflowUseCase:
    def _apply(self, connection, budget_id: str, actor: str, operation_id: str, action,
               *, reason: str | None = None) -> Budget:
        with FinanceUnitOfWork(connection) as uow:
            budget = uow.budgets.get(budget_id)
            if budget is None:
                raise FinanceDomainError("El presupuesto no existe")
            before = {"status": budget.status.value}
            action(budget)
            uow.budgets.update(budget)
            uow.audit(AuditAction.BUDGET_CHANGED, entity_type="budget", entity_id=budget.id,
                      operation_id=operation_id, user_id=actor, before=before,
                      after={"status": budget.status.value}, reason=reason,
                      branch_id=budget.branch_id)
            if budget.status.value == "APPROVED":
                publish_finance_event(uow, EventName.BUDGET_APPROVED, {
                    "budget_id": budget.id, "approved_by": actor, "version": budget.version,
                }, operation_id=operation_id, entity_id=budget.id, branch_id=budget.branch_id)
            return budget

    def submit(self, connection, *, budget_id: str, submitted_by: str,
               operation_id: str) -> Budget:
        return self._apply(connection, budget_id, submitted_by, operation_id,
                           lambda b: b.submit(submitted_by))

    def approve(self, connection, *, budget_id: str, approved_by: str,
                operation_id: str) -> Budget:
        return self._apply(connection, budget_id, approved_by, operation_id,
                           lambda b: b.approve(approved_by))

    def reject(self, connection, *, budget_id: str, rejected_by: str, reason: str,
               operation_id: str) -> Budget:
        return self._apply(connection, budget_id, rejected_by, operation_id,
                           lambda b: b.reject(reason), reason=reason)

    def activate(self, connection, *, budget_id: str, actor: str,
                 operation_id: str) -> Budget:
        return self._apply(connection, budget_id, actor, operation_id, lambda b: b.activate())

    def close(self, connection, *, budget_id: str, actor: str, operation_id: str) -> Budget:
        return self._apply(connection, budget_id, actor, operation_id, lambda b: b.close())

    def cancel(self, connection, *, budget_id: str, actor: str, reason: str,
               operation_id: str) -> Budget:
        return self._apply(connection, budget_id, actor, operation_id,
                           lambda b: b.cancel(reason), reason=reason)
