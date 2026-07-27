"""Accounts payable use cases — segregated lifecycle.

Crear obligación → Programar pago → Autorizar → Ejecutar → Conciliar.
These operations are never combined into a single action.
"""

from __future__ import annotations

import json
from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.entities.payable import Payable, SupplierPayment
from backend.domain.finance.enums import (
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.payable_service import PayableService
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class CreatePayableUseCase:
    def execute(self, connection, *, supplier_id: str, amount: str, currency_code: str = "MXN",
                document_number: str, issue_date: date, due_date: date | None = None,
                branch_id: str | None = None, source_module: str = "finance",
                source_document_id: str | None = None, operation_id: str) -> Payable:
        money = Money.from_string(amount, currency_code)
        with FinanceUnitOfWork(connection) as uow:
            existing = uow.payables.find_by_operation_id(operation_id)
            if existing is not None:
                return existing
            document = FinancialDocument.create(
                FinancialDocumentType.SUPPLIER_INVOICE, document_number, issue_date, money,
                source_module, source_document_id or new_uuid(), new_uuid(),
                branch_id=branch_id, supplier_id=supplier_id, due_date=due_date,
            )
            uow.financial_documents.save(document)
            payable = PayableService().create_obligation(
                supplier_id, document.id, money, issue_date, operation_id,
                due_date=due_date, branch_id=branch_id,
            )
            uow.payables.save(payable)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.PAYABLE_CREATED.value,
                payload_json=json.dumps({
                    "payable_id": payable.id, "supplier_id": supplier_id,
                    "amount": money.to_string(),
                }),
                operation_id=operation_id,
            )
            return payable


class ScheduleSupplierPaymentUseCase:
    def execute(self, connection, *, payable_id: str, amount: str, scheduled_date: date,
                treasury_account_id: str, scheduled_by: str, reference: str = "",
                operation_id: str) -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.supplier_payments.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            payable = uow.payables.get(payable_id)
            if payable is None:
                raise FinanceDomainError("La cuenta por pagar no existe")
            treasury_account = uow.treasury.get(treasury_account_id)
            if treasury_account is None or not treasury_account.active:
                raise FinanceDomainError("La cuenta de tesorería no existe o está inactiva")
            if treasury_account.account_type is TreasuryAccountType.CASH_REGISTER:
                raise FinanceDomainError(
                    "Las compras no se pagan desde Caja POS. Use Tesorería/Capital o CxP."
                )
            money = Money.from_string(amount, payable.original_amount.currency_code)
            if money > payable.outstanding_amount:
                raise FinanceDomainError("El pago programado excede el saldo de la CxP")
            payment = PayableService().schedule_payment(
                payable, money, scheduled_date, treasury_account_id, operation_id,
                scheduled_by=scheduled_by, reference=reference,
            )
            uow.supplier_payments.save(payment)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.SUPPLIER_PAYMENT_SCHEDULED.value,
                payload_json=json.dumps({
                    "payment_id": payment.id, "payable_id": payable_id,
                    "amount": money.to_string(),
                }),
                operation_id=operation_id,
            )
            return payment


class AuthorizeSupplierPaymentUseCase:
    def execute(self, connection, *, payment_id: str, authorized_by: str,
                operation_id: str) -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            payment = uow.supplier_payments.get(payment_id)
            if payment is None:
                raise FinanceDomainError("El pago programado no existe")
            PayableService().authorize_payment(payment, authorized_by)
            uow.supplier_payments.update(payment)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.SUPPLIER_PAYMENT_AUTHORIZED.value,
                payload_json=json.dumps({"payment_id": payment.id,
                                         "authorized_by": authorized_by}),
                operation_id=operation_id,
            )
            return payment


class ExecuteSupplierPaymentUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, payment_id: str, executed_date: date,
                operation_id: str) -> SupplierPayment:
        with FinanceUnitOfWork(connection) as uow:
            payment = uow.supplier_payments.get(payment_id)
            if payment is None:
                raise FinanceDomainError("El pago programado no existe")
            existing = uow.journal_entries.find_by_posting_reference(
                "finance", payment.id, PostingPurpose.SUPPLIER_PAYMENT)
            if existing is not None:
                return payment  # already executed (idempotent)
            payable = uow.payables.get(payment.payable_id)
            if payable is None:
                raise FinanceDomainError("La CxP del pago no existe")
            treasury_account = uow.treasury.get(payment.treasury_account_id)
            profile = uow.posting_profiles.find_effective("PURCHASE", executed_date)
            if profile is None:
                raise FinanceDomainError("No hay perfil contable PURCHASE vigente")

            entry = self._engine.post(
                uow, JournalType.BANK, executed_date,
                f"Pago a proveedor {payment.reference or payment.id[:8]}",
                PostingReference("finance", payment.id, PostingPurpose.SUPPLIER_PAYMENT,
                                 operation_id),
                [
                    LineSpec(profile.account_for("payable_account_id"), debit=payment.amount,
                             description="Cancelación de CxP"),
                    LineSpec(treasury_account.ledger_account_id, credit=payment.amount,
                             description="Salida de tesorería"),
                ],
                branch_id=payment.branch_id,
            )
            PayableService().execute_payment(payment, payable, executed_date, entry.id)
            uow.supplier_payments.update(payment)
            uow.payables.update(payable)
            document = uow.financial_documents.get(payable.financial_document_id)
            if document is not None:
                document.apply_settlement(payment.amount)
                uow.financial_documents.update(document)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.SUPPLIER_PAYMENT_EXECUTED.value,
                payload_json=json.dumps({
                    "payment_id": payment.id, "journal_entry_id": entry.id,
                    "amount": payment.amount.to_string(),
                }),
                operation_id=new_uuid(),
            )
            return payment
