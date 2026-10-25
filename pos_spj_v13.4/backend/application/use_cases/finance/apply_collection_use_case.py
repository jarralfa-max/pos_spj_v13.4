"""ApplyCollectionUseCase — aplica el saldo a favor de un cobro a documentos (§11).

El cobro ya entró a tesorería y lo no aplicado está en Anticipos de clientes;
aplicarlo después mueve ese anticipo a la CxC:

    Dr Anticipos de clientes / Cr Clientes

Repetir la misma operación devuelve lo ya aplicado; la misma clave con otro
contenido es ``CollectionAlreadyAppliedError``; aplicar más de lo disponible
es ``CollectionAmountExceededError``.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance._support import require_profile
from backend.application.use_cases.finance.register_collection_use_case import (
    apply_to_receivables,
)
from backend.domain.finance.enums import AuditAction, JournalType, PostingPurpose
from backend.domain.finance.exceptions import CollectionAlreadyAppliedError, FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid


class ApplyCollectionUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, collection_id: str, applications: list[dict],
                application_date: date, operation_id: str,
                applied_by: str | None = None) -> list:
        if not applications:
            raise FinanceDomainError("Indique a qué documentos se aplica el cobro")
        with FinanceUnitOfWork(connection) as uow:
            previous = uow.collections.find_application_by_operation_id(f"{operation_id}:0")
            if previous is not None:
                first = applications[0]
                if previous.receivable_id != str(first["receivable_id"]) or \
                        previous.applied_amount.amount != Money.from_string(
                            str(first["amount"]), previous.applied_amount.currency_code).amount:
                    raise CollectionAlreadyAppliedError(
                        f"La operación {operation_id} ya aplicó otro importe")
                return uow.collections.list_applications(collection_id=collection_id)
            collection = uow.collections.get(collection_id)
            if collection is None:
                raise FinanceDomainError("El cobro no existe")
            applied = apply_to_receivables(uow, collection, applications,
                                           operation_id=operation_id, applied_by=applied_by)
            profile = require_profile(uow, "SALE", application_date,
                                      branch_id=collection.branch_id)
            total = Money.zero(collection.amount.currency_code)
            credit_lines = []
            for application, receivable in applied:
                total = total.add(application.applied_amount)
                credit_lines.append(LineSpec(
                    profile.account_for("receivable_account_id"),
                    credit=application.applied_amount, description="Aplicación de anticipo",
                    customer_id=collection.customer_id,
                    source_reference=receivable.financial_document_id))
            entry = self._engine.post(
                uow, JournalType.GENERAL, application_date,
                f"Aplicación de anticipo del cobro {collection.reference or collection.id[-8:]}",
                PostingReference("finance", new_uuid(),
                                 PostingPurpose.CUSTOMER_ADVANCE_APPLICATION, operation_id),
                [LineSpec(profile.account_for("customer_advance_account_id"), debit=total,
                          description="Saldo a favor aplicado",
                          customer_id=collection.customer_id)] + credit_lines,
                currency_code=total.currency_code, branch_id=collection.branch_id,
                created_by=applied_by)
            uow.collections.update(collection)
            for application, _ in applied:
                application.journal_entry_id = entry.id
                uow.collections.save_application(application)
            uow.audit(AuditAction.COLLECTION_APPLIED, entity_type="collection",
                      entity_id=collection.id, operation_id=operation_id, user_id=applied_by,
                      after={"applied_total": total.to_string(),
                             "unapplied": collection.unapplied().to_string(),
                             "receivables": [r.id for _, r in applied]},
                      branch_id=collection.branch_id)
            return [application for application, _ in applied]
