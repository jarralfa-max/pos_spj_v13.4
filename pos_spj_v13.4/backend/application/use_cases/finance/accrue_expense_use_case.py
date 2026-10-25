"""Devengo y cancelación de una solicitud de gasto APROBADA (§16).

Devengar = llegó el documento del gasto. Dos formas, ambas con asiento:

- a crédito: se crea la CxP del proveedor (Dr gasto / Cr Proveedores); el pago
  posterior de esa CxP liquida la solicitud y mueve el presupuesto a «pagado»;
- pagado en el acto: Dr gasto / Cr Tesorería (con saldo suficiente) y la
  solicitud queda liquidada de inmediato.

El compromiso se libera por lo devengado (sin contarlo dos veces). Cancelar
una solicitud aprobada libera su compromiso.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import (
    assert_available_funds,
    require_treasury,
)
from backend.application.use_cases.finance.create_payable_use_case import create_payable_in
from backend.domain.finance.enums import (
    AuditAction,
    ExpenseRequestStatus,
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
    PurchaseDebitNature,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.budget_service import BudgetDomainService
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


def _load(uow: FinanceUnitOfWork, expense_request_id: str):
    request = uow.expense_requests.get(expense_request_id)
    if request is None:
        raise FinanceDomainError("La solicitud de gasto no existe")
    return request


def _dims(request) -> dict:
    return {"cost_center_id": request.cost_center_id, "project_id": request.project_id,
            "department_id": request.department_id}


class AccrueExpenseUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, expense_request_id: str, document_reference: str,
                accrual_date: date, operation_id: str, accrued_by: str,
                amount: str | None = None, supplier_id: str | None = None,
                due_date: date | None = None,
                paid_from_treasury_account_id: str | None = None) -> str:
        if bool(supplier_id) == bool(paid_from_treasury_account_id):
            raise FinanceDomainError(
                "El gasto se devenga a crédito de un proveedor o pagado desde una cuenta de "
                "tesorería (uno de los dos)")
        with FinanceUnitOfWork(connection) as uow:
            request = _load(uow, expense_request_id)
            if request.status is ExpenseRequestStatus.ACCRUED or \
                    request.status is ExpenseRequestStatus.SETTLED:
                # Reintento de la MISMA operación: mismo asiento. Otra operación sobre
                # un gasto ya devengado sería un segundo devengo: se rechaza.
                accrual = uow.journal_entries.get(request.accrual_journal_entry_id) \
                    if request.accrual_journal_entry_id else None
                if accrual is not None and \
                        accrual.posting_reference.operation_id == operation_id:
                    return accrual.id
                raise FinanceDomainError(
                    f"La solicitud ya está {request.status.value}: no se devenga dos veces")
            money = Money.from_string(amount, request.amount.currency_code) if amount \
                else request.amount
            budget = uow.budgets.get(request.budget_id) if request.budget_id else None
            entry_id: str
            payable_id = None
            if supplier_id:
                payable = create_payable_in(
                    uow, supplier_id=supplier_id, amount=money.to_string(),
                    currency_code=money.currency_code, document_number=document_reference,
                    issue_date=accrual_date, due_date=due_date, branch_id=request.branch_id,
                    source_module="finance", source_document_id=request.id,
                    operation_id=f"{operation_id}:payable",
                    debit_nature=PurchaseDebitNature.OPERATING_EXPENSE)
                payable_id = payable.id
                profile = uow.posting_profiles.find_effective(
                    "PURCHASE", accrual_date, branch_id=request.branch_id)
                if profile is None:
                    raise FinanceDomainError("No hay perfil contable PURCHASE vigente")
                credit_account = profile.account_for("payable_account_id")
            else:
                treasury = require_treasury(uow, paid_from_treasury_account_id,
                                            currency_code=money.currency_code)
                assert_available_funds(uow, treasury, money)
                credit_account = treasury.ledger_account_id
            entry = self._engine.post(
                uow, JournalType.PURCHASES if supplier_id else JournalType.BANK, accrual_date,
                f"Gasto {request.description or request.category or document_reference}".strip(),
                PostingReference("finance", request.id, PostingPurpose.EXPENSE_ACCRUAL,
                                 operation_id),
                [LineSpec(request.account_id, debit=money,
                          description=f"Gasto según {document_reference}",
                          supplier_id=supplier_id, branch_id=request.branch_id,
                          source_reference=document_reference, **_dims(request)),
                 LineSpec(credit_account, credit=money, description=document_reference,
                          supplier_id=supplier_id, branch_id=request.branch_id)],
                currency_code=money.currency_code, branch_id=request.branch_id,
                created_by=accrued_by,
                source_document_type=FinancialDocumentType.EXPENSE_DOCUMENT.value)
            entry_id = entry.id
            committed = request.amount if money >= request.amount else money
            request.accrue(money, document_reference, payable_id=payable_id,
                           journal_entry_id=entry_id)
            if budget is not None:
                BudgetDomainService(uow.settings.budget_warning_percent).accrue(
                    budget, request.account_id, request.period_code, money,
                    from_commitment=committed, excess_authorized=request.excess_authorized,
                    **_dims(request))
                if money < request.amount:
                    BudgetDomainService().release(budget, request.account_id,
                                                  request.period_code,
                                                  request.amount.subtract(money),
                                                  **_dims(request))
            if paid_from_treasury_account_id:
                request.settle(money)
                if budget is not None:
                    BudgetDomainService().pay(budget, request.account_id, request.period_code,
                                              money, **_dims(request))
            if budget is not None:
                uow.budgets.update(budget)
            uow.expense_requests.update(request)
            uow.audit(AuditAction.EXPENSE_DECIDED, entity_type="expense_request",
                      entity_id=request.id, operation_id=operation_id, user_id=accrued_by,
                      before={"status": "APPROVED"},
                      after={"status": request.status.value, "accrued": money.to_string(),
                             "journal_entry_id": entry_id, "payable_id": payable_id},
                      branch_id=request.branch_id)
            publish_finance_event(uow, EventName.BUDGET_ACCRUED, {
                "expense_request_id": request.id, "amount": money.to_string(),
                "document_reference": document_reference, "journal_entry_id": entry_id,
            }, operation_id=operation_id, entity_id=request.id, branch_id=request.branch_id)
            if request.status is ExpenseRequestStatus.SETTLED:
                publish_finance_event(uow, EventName.EXPENSE_SETTLED, {
                    "expense_request_id": request.id, "amount": money.to_string(),
                }, operation_id=operation_id, entity_id=request.id, branch_id=request.branch_id)
            return entry_id


class CancelExpenseUseCase:
    def execute(self, connection, *, expense_request_id: str, reason: str, operation_id: str,
                cancelled_by: str) -> None:
        with FinanceUnitOfWork(connection) as uow:
            request = _load(uow, expense_request_id)
            was_approved = request.status is ExpenseRequestStatus.APPROVED
            before = {"status": request.status.value}
            request.cancel(reason)
            if was_approved and request.budget_id:
                budget = uow.budgets.get(request.budget_id)
                if budget is not None:
                    BudgetDomainService().release(budget, request.account_id,
                                                  request.period_code, request.amount,
                                                  **_dims(request))
                    uow.budgets.update(budget)
                    publish_finance_event(uow, EventName.BUDGET_COMMITMENT_RELEASED, {
                        "expense_request_id": request.id, "amount": request.amount.to_string(),
                        "reason": reason,
                    }, operation_id=operation_id, entity_id=request.id,
                        branch_id=request.branch_id)
            uow.expense_requests.update(request)
            uow.audit(AuditAction.EXPENSE_DECIDED, entity_type="expense_request",
                      entity_id=request.id, operation_id=operation_id, user_id=cancelled_by,
                      before=before, after={"status": request.status.value}, reason=reason,
                      branch_id=request.branch_id)
