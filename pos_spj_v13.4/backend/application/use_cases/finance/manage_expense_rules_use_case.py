"""Reglas de aprobación de gasto (§16): cuántas aprobaciones según importe,
sucursal, categoría, centro de costo y solicitante. Configuración auditada."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.finance.entities.expense import ExpenseApprovalRule
from backend.domain.finance.enums import AuditAction
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class ManageExpenseRulesUseCase:
    def create(self, connection, *, name: str, min_amount: str, required_approvals: int,
               operation_id: str, created_by: str, branch_id: str | None = None,
               category: str | None = None, cost_center_id: str | None = None,
               requester_id: str | None = None, priority: int = 0) -> ExpenseApprovalRule:
        rule = ExpenseApprovalRule.create(
            name, min_amount=Decimal(str(min_amount or "0")),
            required_approvals=required_approvals, branch_id=branch_id, category=category,
            cost_center_id=cost_center_id, requester_id=requester_id, priority=priority)
        with FinanceUnitOfWork(connection) as uow:
            uow.expense_requests.save_rule(rule)
            uow.audit(AuditAction.SETTINGS_UPDATED, entity_type="expense_approval_rule",
                      entity_id=rule.id, operation_id=operation_id, user_id=created_by,
                      after={"name": rule.name, "min_amount": format(rule.min_amount, "f"),
                             "required_approvals": rule.required_approvals,
                             "branch_id": branch_id, "category": rule.category,
                             "cost_center_id": cost_center_id, "requester_id": requester_id})
        return rule

    def deactivate(self, connection, *, rule_id: str, operation_id: str, actor: str,
                   reason: str = "") -> None:
        with FinanceUnitOfWork(connection) as uow:
            uow.expense_requests.deactivate_rule(rule_id)
            uow.audit(AuditAction.SETTINGS_UPDATED, entity_type="expense_approval_rule",
                      entity_id=rule_id, operation_id=operation_id, user_id=actor,
                      after={"active": False}, reason=reason)
