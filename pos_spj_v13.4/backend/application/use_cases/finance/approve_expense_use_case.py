"""ApproveExpenseUseCase — aprobación por reglas y compromiso presupuestal (§16).

Cada aprobación es de una persona distinta (y nunca del solicitante). Con la
última aprobación requerida, la solicitud queda APROBADA y compromete el
presupuesto; exceder un presupuesto bloqueante exige autorización de exceso
(permiso propio + motivo, en la capa de comandos). Rechazar exige motivo.
"""

from __future__ import annotations

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.application.use_cases.finance.commit_budget_use_case import CommitBudgetUseCase
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


def _load(uow: FinanceUnitOfWork, expense_request_id: str):
    request = uow.expense_requests.get(expense_request_id)
    if request is None:
        raise FinanceDomainError("La solicitud de gasto no existe")
    return request


class ApproveExpenseUseCase:
    def approve(self, connection, *, expense_request_id: str, approver_id: str,
                operation_id: str, reason: str = "", excess_authorized: bool = False) -> bool:
        with FinanceUnitOfWork(connection) as uow:
            request = _load(uow, expense_request_id)
            before = {"status": request.status.value, "approvals": request.approval_count()}
            approved = request.approve(approver_id, reason)
            level = None
            if approved:
                budget = uow.budgets.get(request.budget_id)
                if budget is None:
                    raise FinanceDomainError("El presupuesto de la solicitud ya no existe")
                request.excess_authorized = bool(excess_authorized)
                level = CommitBudgetUseCase().commit_in(
                    uow, budget, account_id=request.account_id,
                    period_code=request.period_code, amount=request.amount,
                    operation_id=operation_id, entity_id=request.id,
                    excess_authorized=excess_authorized,
                    cost_center_id=request.cost_center_id, project_id=request.project_id,
                    department_id=request.department_id)
            uow.expense_requests.update(request)
            uow.audit(AuditAction.EXPENSE_DECIDED, entity_type="expense_request",
                      entity_id=request.id, operation_id=operation_id, user_id=approver_id,
                      before=before,
                      after={"status": request.status.value,
                             "approvals": request.approval_count(),
                             "control_level": level.value if level else None,
                             "excess_authorized": request.excess_authorized},
                      reason=reason, branch_id=request.branch_id)
            if approved:
                publish_finance_event(uow, EventName.EXPENSE_APPROVED, {
                    "expense_request_id": request.id, "amount": request.amount.to_string(),
                    "approvals": request.approval_count(),
                }, operation_id=operation_id, entity_id=request.id, branch_id=request.branch_id)
            return approved

    def reject(self, connection, *, expense_request_id: str, approver_id: str, reason: str,
               operation_id: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            request = _load(uow, expense_request_id)
            before = {"status": request.status.value}
            request.reject(approver_id, reason)
            uow.expense_requests.update(request)
            uow.audit(AuditAction.EXPENSE_DECIDED, entity_type="expense_request",
                      entity_id=request.id, operation_id=operation_id, user_id=approver_id,
                      before=before, after={"status": request.status.value}, reason=reason,
                      branch_id=request.branch_id)
            publish_finance_event(uow, EventName.EXPENSE_REJECTED, {
                "expense_request_id": request.id, "reason": reason,
            }, operation_id=operation_id, entity_id=request.id, branch_id=request.branch_id)
