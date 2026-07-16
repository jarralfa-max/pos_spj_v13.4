"""Accounts receivable use cases — create receivables and register collections."""

from __future__ import annotations

import json
from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.entities.receivable import Receivable
from backend.domain.finance.enums import (
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
    TreasuryAccountType,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.receivable_service import ReceivableService
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class CreateReceivableUseCase:
    """Creates a receivable (with its source document) outside the sale flow."""

    def execute(self, connection, *, customer_id: str, amount: str, currency_code: str = "MXN",
                document_number: str, issue_date: date, due_date: date | None = None,
                branch_id: str | None = None, source_module: str = "finance",
                source_document_id: str | None = None, operation_id: str) -> Receivable:
        money = Money.from_string(amount, currency_code)
        with FinanceUnitOfWork(connection) as uow:
            existing = uow.receivables.find_by_operation_id(operation_id)
            if existing is not None:
                return existing
            document = FinancialDocument.create(
                FinancialDocumentType.SALES_INVOICE, document_number, issue_date, money,
                source_module, source_document_id or new_uuid(), new_uuid(),
                branch_id=branch_id, customer_id=customer_id, due_date=due_date,
            )
            uow.financial_documents.save(document)
            receivable = Receivable.create(
                customer_id, document.id, money, issue_date, operation_id,
                due_date=due_date, branch_id=branch_id,
            )
            uow.receivables.save(receivable)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.RECEIVABLE_CREATED.value,
                payload_json=json.dumps({
                    "receivable_id": receivable.id, "customer_id": customer_id,
                    "amount": money.to_string(), "currency_code": currency_code,
                }),
                operation_id=operation_id,
            )
            return receivable


class RegisterCollectionUseCase:
    """Registers a customer payment: updates CxC and posts Dr treasury / Cr CxC."""

    def __init__(self) -> None:
        self._engine = PostingEngine()
        self._domain = ReceivableService()

    def execute(self, connection, *, receivable_id: str, amount: str,
                treasury_account_id: str, collection_date: date,
                reference: str = "", operation_id: str) -> str:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.collections.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate.id
            receivable = uow.receivables.get(receivable_id)
            if receivable is None:
                raise FinanceDomainError("La cuenta por cobrar no existe")
            treasury_account = uow.treasury.get(treasury_account_id)
            if treasury_account is None or not treasury_account.active:
                raise FinanceDomainError("La cuenta de tesorería no existe o está inactiva")
            if treasury_account.account_type is TreasuryAccountType.DIGITAL_WALLET:
                raise FinanceDomainError(
                    "Un monedero promocional no puede recibir cobros de clientes"
                )
            money = Money.from_string(amount, receivable.original_amount.currency_code)

            collection = self._domain.register_collection(
                receivable, money, collection_date, treasury_account_id, operation_id,
                reference=reference,
            )
            document = uow.financial_documents.get(receivable.financial_document_id)
            if document is not None:
                document.apply_settlement(money)
                uow.financial_documents.update(document)

            profile = self._resolve_sale_profile(uow, collection_date)
            entry = self._engine.post(
                uow, JournalType.CASH, collection_date,
                f"Cobro CxC {reference or receivable.id[:8]}",
                PostingReference("finance", collection.id, PostingPurpose.COLLECTION,
                                 new_uuid()),
                [
                    LineSpec(treasury_account.ledger_account_id, debit=money,
                             description="Entrada de tesorería por cobro"),
                    LineSpec(profile.account_for("receivable_account_id"), credit=money,
                             description="Aplicación a cuentas por cobrar"),
                ],
                branch_id=receivable.branch_id,
            )
            collection.journal_entry_id = entry.id
            uow.collections.save(collection)
            uow.receivables.update(receivable)

            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.COLLECTION_REGISTERED.value,
                payload_json=json.dumps({
                    "collection_id": collection.id, "receivable_id": receivable.id,
                    "amount": money.to_string(),
                    "outstanding": receivable.outstanding_amount.to_string(),
                }),
                operation_id=operation_id,
            )
            if receivable.outstanding_amount.is_zero():
                uow.outbox.enqueue(
                    event_id=new_uuid(), event_name=EventName.RECEIVABLE_SETTLED.value,
                    payload_json=json.dumps({"receivable_id": receivable.id}),
                    operation_id=new_uuid(),
                )
            return collection.id

    @staticmethod
    def _resolve_sale_profile(uow: FinanceUnitOfWork, on_date: date):
        profile = uow.posting_profiles.find_effective("SALE", on_date)
        if profile is None:
            raise FinanceDomainError("No hay perfil contable SALE vigente")
        return profile
