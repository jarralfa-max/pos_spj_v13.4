"""ExecuteSupplierPaymentUseCase — ejecutar un pago TOTALMENTE autorizado (§12, §13, §28).

- Revalida el contexto (lo autorizado ayer puede no valer hoy).
- Exige evidencia externa (folio SPEI, cheque, recibo) que queda con quien ejecutó.
- Doble control: quien autorizó no ejecuta (configurable).
- Saldo suficiente en la cuenta de tesorería (salvo sobregiro pactado).
- Pronto pago: si aplica, el descuento liquida parte de la deuda sin salir dinero.

    Dr Proveedores (pago + descuento) / Cr Tesorería (pago) / Cr Descuentos obtenidos
"""

from __future__ import annotations

from datetime import date

from backend.application.finance.ports import SupplierDirectoryPort
from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import (
    assert_available_funds,
    require_profile,
)
from backend.application.use_cases.finance.schedule_supplier_payment_use_case import (
    validate_payment_context,
)
from backend.domain.finance.entities.payable import SupplierPayment
from backend.domain.finance.enums import AuditAction, JournalType, PostingPurpose
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    PayableNotFoundError,
    PaymentAuthorizationError,
)
from backend.domain.finance.policies.payment_authorization_policy import PaymentAuthorizationPolicy
from backend.domain.finance.policies.segregation_policy import SegregationPolicy
from backend.domain.finance.services.budget_service import BudgetDomainService
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.payable_service import PayableService
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class ExecuteSupplierPaymentUseCase:
    def __init__(self, supplier_directory: SupplierDirectoryPort) -> None:
        self._engine = PostingEngine()
        self._directory = supplier_directory

    def execute(self, connection, *, payment_id: str, executed_date: date,
                operation_id: str, executed_by: str | None = None,
                execution_reference: str = "") -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            payment = uow.supplier_payments.get(payment_id)
            if payment is None:
                raise FinanceDomainError("El pago programado no existe")
            existing = uow.journal_entries.find_by_posting_reference(
                "finance", payment.id, PostingPurpose.SUPPLIER_PAYMENT)
            if existing is not None and payment.journal_entry_id == existing.id:
                return payment  # reintento de la misma ejecución
            if not (execution_reference or "").strip():
                raise PaymentAuthorizationError(
                    "Registre la evidencia del pago (folio SPEI, cheque o recibo); "
                    "sin ella el pago no se marca como ejecutado")
            payable = uow.payables.get(payment.payable_id)
            if payable is None:
                raise PayableNotFoundError("La CxP del pago no existe")
            PaymentAuthorizationPolicy().enforce_execution(payment, payable)
            SegregationPolicy(uow.settings).enforce_payment_execution(
                authorized_by=payment.authorized_by,
                second_authorized_by=payment.second_authorized_by, executor=executed_by)
            treasury = validate_payment_context(
                uow, self._directory, payable=payable,
                treasury_account_id=payment.treasury_account_id, amount=payment.amount)
            discount = payable.early_payment_discount(executed_date, payment.amount)
            if payment.amount.add(discount) > payable.outstanding_amount:
                raise FinanceDomainError(
                    "El pago excede el saldo vigente de la CxP; vuelva a programarlo")
            assert_available_funds(uow, treasury, payment.amount)
            profile = require_profile(uow, "PURCHASE", executed_date, branch_id=payment.branch_id)
            evidence = execution_reference.strip()
            lines = [
                LineSpec(profile.account_for("payable_account_id"),
                         debit=payment.amount.add(discount), description="Cancelación de CxP",
                         supplier_id=payment.supplier_id),
                LineSpec(treasury.ledger_account_id, credit=payment.amount,
                         description=f"Salida de tesorería ({evidence})",
                         supplier_id=payment.supplier_id, source_reference=evidence),
            ]
            if discount.is_positive():
                lines.append(LineSpec(profile.account_for("early_payment_discount_account_id"),
                                      credit=discount, description="Descuento por pronto pago",
                                      supplier_id=payment.supplier_id))
            entry = self._engine.post(
                uow, JournalType.BANK, executed_date,
                f"Pago a proveedor {payment.reference or payment.id[-8:]}",
                PostingReference("finance", payment.id, PostingPurpose.SUPPLIER_PAYMENT,
                                 operation_id),
                lines, currency_code=payment.amount.currency_code,
                branch_id=payment.branch_id, created_by=executed_by)
            PayableService().execute_payment(
                payment, payable, executed_date, entry.id, executed_by=executed_by,
                execution_reference=evidence,
                discount_amount=discount if discount.is_positive() else None)
            uow.supplier_payments.update(payment)
            uow.payables.update(payable)
            document = uow.financial_documents.get(payable.financial_document_id)
            if document is not None:
                document.apply_settlement(payment.amount.add(discount))
                uow.financial_documents.update(document)
            self._settle_expense(uow, payable, payment.amount.add(discount))
            uow.audit(AuditAction.PAYMENT_EXECUTED, entity_type="supplier_payment",
                      entity_id=payment.id, operation_id=operation_id, user_id=executed_by,
                      before={"status": "AUTHORIZED"},
                      after={"status": payment.status.value, "journal_entry_id": entry.id,
                             "amount": payment.amount.to_string(),
                             "discount": discount.to_string(),
                             "execution_reference": evidence},
                      branch_id=payment.branch_id)
            publish_finance_event(uow, EventName.SUPPLIER_PAYMENT_EXECUTED, {
                "payment_id": payment.id, "journal_entry_id": entry.id,
                "amount": payment.amount.to_string(), "discount": discount.to_string(),
                "execution_reference": evidence, "executed_by": executed_by,
            }, operation_id=operation_id, entity_id=payment.id, branch_id=payment.branch_id)
            if payable.outstanding_amount.is_zero():
                publish_finance_event(uow, EventName.PAYABLE_SETTLED, {
                    "payable_id": payable.id, "supplier_id": payable.supplier_id,
                }, operation_id=operation_id, entity_id=payable.id, branch_id=payable.branch_id)
            return payment

    @staticmethod
    def _settle_expense(uow: FinanceUnitOfWork, payable, amount) -> None:
        """Si la CxP nació de una solicitud de gasto devengada, el pago la liquida
        y mueve el presupuesto de devengado a pagado (§16)."""
        request = uow.expense_requests.find_by_payable(payable.id)
        if request is None or request.status.value != "ACCRUED":
            return
        settle = amount if amount <= request.accrued_amount.subtract(request.settled_amount) \
            else request.accrued_amount.subtract(request.settled_amount)
        if not settle.is_positive():
            return
        request.settle(settle)
        uow.expense_requests.update(request)
        if request.budget_id:
            budget = uow.budgets.get(request.budget_id)
            if budget is not None:
                BudgetDomainService().pay(budget, request.account_id, request.period_code,
                                          settle, cost_center_id=request.cost_center_id,
                                          project_id=request.project_id,
                                          department_id=request.department_id)
                uow.budgets.update(budget)
        if request.status.value == "SETTLED":
            publish_finance_event(uow, EventName.EXPENSE_SETTLED, {
                "expense_request_id": request.id, "payable_id": payable.id,
                "amount": request.settled_amount.to_string(),
            }, operation_id=request.operation_id, entity_id=request.id,
                branch_id=request.branch_id)
