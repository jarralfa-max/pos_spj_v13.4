"""CreateReceivableUseCase — CxC con su documento fuente (§10, §11).

Auditoría d9f2bca F11: una CxC creada desde Finanzas declara su contrapartida
y nace con asiento de reconocimiento (Dr Clientes / Cr contrapartida); sólo
Ventas, que la reconoce en su propio asiento de venta, la crea sin ella.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.application.use_cases.finance._support import require_profile
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.entities.receivable import Receivable
from backend.domain.finance.enums import (
    AuditAction,
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
)
from backend.domain.finance.exceptions import FinanceDomainError, IdempotencyConflictError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

#: Módulos operativos que reconocen la deuda en su propio asiento.
SELF_RECOGNIZING_SOURCES = frozenset({"sales"})


def create_receivable_in(uow: FinanceUnitOfWork, *, customer_id: str, money: Money,
                         document_number: str, issue_date: date, due_date: date | None,
                         branch_id: str | None, source_module: str,
                         source_document_id: str | None, operation_id: str,
                         credit_term_days: int | None = None, credit_origin: str = "SALE",
                         document_type: FinancialDocumentType =
                         FinancialDocumentType.CUSTOMER_INVOICE) -> Receivable:
    """Documento + CxC + evento dentro de una unidad de trabajo YA abierta."""
    if due_date is None and credit_term_days is not None:
        due_date = issue_date + timedelta(days=int(credit_term_days))
    document = FinancialDocument.create(
        document_type, document_number, issue_date, money,
        source_module, source_document_id or new_uuid(), new_uuid(),
        branch_id=branch_id, customer_id=customer_id, due_date=due_date,
    )
    uow.financial_documents.save(document)
    receivable = Receivable.create(
        customer_id, document.id, money, issue_date, operation_id,
        due_date=due_date, branch_id=branch_id, credit_term_days=credit_term_days,
        credit_origin=credit_origin,
    )
    uow.receivables.save(receivable)
    publish_finance_event(uow, EventName.RECEIVABLE_CREATED, {
        "receivable_id": receivable.id, "customer_id": customer_id,
        "amount": money.to_string(), "currency_code": money.currency_code,
        "due_date": due_date.isoformat() if due_date else None,
        "source_module": source_module, "source_document_id": document.source_document_id,
    }, operation_id=operation_id, entity_id=receivable.id, branch_id=branch_id,
        source_document_id=document.id)
    return receivable


class CreateReceivableUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, customer_id: str, amount: str, currency_code: str = "MXN",
                document_number: str, issue_date: date, due_date: date | None = None,
                credit_term_days: int | None = None, branch_id: str | None = None,
                source_module: str = "finance", source_document_id: str | None = None,
                operation_id: str, owns_transaction: bool = True,
                counterpart_account_id: str | None = None,
                created_by: str | None = None) -> Receivable:
        money = Money.from_string(amount, currency_code)
        if counterpart_account_id is None and source_module not in SELF_RECOGNIZING_SOURCES:
            raise FinanceDomainError(
                "Una cuenta por cobrar creada desde Finanzas debe declarar la cuenta de "
                "contrapartida de su reconocimiento; sin asiento el auxiliar y el mayor "
                "dejarían de cuadrar")
        with FinanceUnitOfWork(connection, owns_transaction=owns_transaction) as uow:
            existing = uow.receivables.find_by_operation_id(operation_id)
            if existing is not None:
                if (existing.customer_id != customer_id
                        or existing.original_amount.currency_code != money.currency_code
                        or existing.original_amount.amount != money.amount):
                    raise IdempotencyConflictError(
                        f"La operación {operation_id} ya creó otra CxC; no se acepta "
                        f"{money.to_string()} con la misma clave")
                return existing
            receivable = create_receivable_in(
                uow, customer_id=customer_id, money=money, document_number=document_number,
                issue_date=issue_date, due_date=due_date, branch_id=branch_id,
                source_module=source_module, source_document_id=source_document_id,
                operation_id=operation_id, credit_term_days=credit_term_days,
                credit_origin="MANUAL" if source_module == "finance" else "SALE")
            if counterpart_account_id is not None:
                profile = require_profile(uow, "SALE", issue_date, branch_id=branch_id)
                self._engine.post(
                    uow, JournalType.GENERAL, issue_date,
                    f"Reconocimiento CxC {document_number}",
                    PostingReference("finance", receivable.id,
                                     PostingPurpose.RECEIVABLE_RECOGNITION, operation_id),
                    [LineSpec(profile.account_for("receivable_account_id"), debit=money,
                              description=f"CxC {document_number}", customer_id=customer_id),
                     LineSpec(counterpart_account_id, credit=money,
                              description=f"Contrapartida CxC {document_number}")],
                    currency_code=money.currency_code, branch_id=branch_id,
                    created_by=created_by,
                    source_document_type=FinancialDocumentType.CUSTOMER_INVOICE.value,
                )
            uow.audit(AuditAction.RECEIVABLE_CREATED, entity_type="receivable",
                      entity_id=receivable.id, operation_id=operation_id, user_id=created_by,
                      after={"customer_id": customer_id, "amount": money.to_string(),
                             "document_number": document_number,
                             "due_date": receivable.due_date.isoformat()
                             if receivable.due_date else None},
                      branch_id=branch_id)
            return receivable
