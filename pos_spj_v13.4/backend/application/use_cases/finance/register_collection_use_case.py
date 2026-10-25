"""RegisterCollectionUseCase — cobro recibido y su aplicación EXPLÍCITA (§11).

Un cobro entra a una cuenta de tesorería y se aplica a uno o varios
documentos del cliente. Lo que no se aplica queda como anticipo (saldo a favor
del cliente, cuenta 2140), nunca como ingreso ni como cobro perdido:

    Dr Tesorería                  importe del cobro
        Cr Clientes               suma aplicada (por documento)
        Cr Anticipos de clientes  no aplicado

Reglas: suma aplicada ≤ importe del cobro; aplicación ≤ saldo de cada CxC;
mismo cliente y misma moneda; idempotente por ``operation_id``.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import require_profile, require_treasury
from backend.domain.finance.entities.receivable import Collection
from backend.domain.finance.enums import AuditAction, JournalType, PostingPurpose
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    IdempotencyConflictError,
    ReceivableNotFoundError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.receivable_service import ReceivableService
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


def apply_to_receivables(uow: FinanceUnitOfWork, collection: Collection,
                         applications: list[dict], *, operation_id: str,
                         applied_by: str | None) -> list:
    """Aplica partes del cobro a CxC del mismo cliente; actualiza documentos y
    publica COLLECTION_APPLIED / RECEIVABLE_SETTLED. No contabiliza: quien llama
    arma el asiento con la suma aplicada."""
    created = []
    seen: set[str] = set()
    for index, item in enumerate(applications):
        receivable_id = str(item["receivable_id"])
        if receivable_id in seen:
            raise FinanceDomainError("Una CxC aparece dos veces en la misma aplicación")
        seen.add(receivable_id)
        receivable = uow.receivables.get(receivable_id)
        if receivable is None:
            raise ReceivableNotFoundError("La cuenta por cobrar no existe")
        amount = Money.from_string(str(item["amount"]), collection.amount.currency_code)
        application = ReceivableService.apply(
            collection, receivable, amount, f"{operation_id}:{index}", created_by=applied_by)
        uow.receivables.update(receivable)
        document = uow.financial_documents.get(receivable.financial_document_id)
        if document is not None:
            document.apply_settlement(amount)
            uow.financial_documents.update(document)
        created.append((application, receivable))
        publish_finance_event(uow, EventName.COLLECTION_APPLIED, {
            "collection_id": collection.id, "receivable_id": receivable.id,
            "applied_amount": amount.to_string(),
            "outstanding": receivable.outstanding_amount.to_string(),
        }, operation_id=application.operation_id, entity_id=application.id,
            branch_id=receivable.branch_id, source_document_id=collection.id)
        if receivable.outstanding_amount.is_zero():
            publish_finance_event(uow, EventName.RECEIVABLE_SETTLED, {
                "receivable_id": receivable.id, "customer_id": receivable.customer_id,
            }, operation_id=application.operation_id, entity_id=receivable.id,
                branch_id=receivable.branch_id)
    return created


class RegisterCollectionUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, customer_id: str, amount: str, treasury_account_id: str,
                collection_date: date, operation_id: str,
                applications: list[dict] | None = None, reference: str = "",
                payment_method: str = "BANK_TRANSFER", currency_code: str = "MXN",
                branch_id: str | None = None, created_by: str | None = None) -> Collection:
        applications = list(applications or [])
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.collections.find_by_operation_id(operation_id)
            if duplicate is not None:
                if duplicate.customer_id != customer_id or duplicate.amount.amount != \
                        Money.from_string(amount, duplicate.amount.currency_code).amount:
                    raise IdempotencyConflictError(
                        f"La operación {operation_id} ya registró otro cobro")
                return duplicate
            treasury = require_treasury(uow, treasury_account_id, currency_code=currency_code)
            money = Money.from_string(amount, treasury.currency_code)
            collection = Collection.create(
                customer_id, money, collection_date, treasury.id, operation_id,
                reference=reference, branch_id=branch_id or treasury.branch_id,
                payment_method=payment_method, created_by=created_by)
            uow.collections.save(collection)
            applied = apply_to_receivables(uow, collection, applications,
                                           operation_id=operation_id, applied_by=created_by)
            profile = require_profile(uow, "SALE", collection_date,
                                      branch_id=collection.branch_id)
            lines = [LineSpec(treasury.ledger_account_id, debit=money,
                              description=f"Cobro {reference}".strip(),
                              customer_id=customer_id, source_reference=reference)]
            for application, receivable in applied:
                lines.append(LineSpec(profile.account_for("receivable_account_id"),
                                      credit=application.applied_amount,
                                      description="Aplicación a cuentas por cobrar",
                                      customer_id=customer_id,
                                      source_reference=receivable.financial_document_id))
            unapplied = collection.unapplied()
            if unapplied.is_positive():
                lines.append(LineSpec(profile.account_for("customer_advance_account_id"),
                                      credit=unapplied,
                                      description="Anticipo / saldo a favor del cliente",
                                      customer_id=customer_id))
            entry = self._engine.post(
                uow, JournalType.CASH, collection_date,
                f"Cobro a cliente {reference or collection.id[-8:]}",
                PostingReference("finance", collection.id, PostingPurpose.COLLECTION,
                                 operation_id),
                lines, currency_code=money.currency_code, branch_id=collection.branch_id,
                created_by=created_by)
            collection.journal_entry_id = entry.id
            uow.collections.update(collection)
            for application, _ in applied:
                application.journal_entry_id = entry.id
                uow.collections.save_application(application)
            uow.audit(AuditAction.COLLECTION_REGISTERED, entity_type="collection",
                      entity_id=collection.id, operation_id=operation_id, user_id=created_by,
                      after={"customer_id": customer_id, "amount": money.to_string(),
                             "applied": collection.applied_amount.to_string(),
                             "unapplied": unapplied.to_string(),
                             "treasury_account_id": treasury.id, "reference": reference},
                      branch_id=collection.branch_id)
            publish_finance_event(uow, EventName.COLLECTION_REGISTERED, {
                "collection_id": collection.id, "customer_id": customer_id,
                "amount": money.to_string(), "applied": collection.applied_amount.to_string(),
                "unapplied": unapplied.to_string(), "journal_entry_id": entry.id,
            }, operation_id=operation_id, entity_id=collection.id,
                branch_id=collection.branch_id)
            return collection
