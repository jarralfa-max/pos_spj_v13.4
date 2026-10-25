"""WriteOffReceivableUseCase — castigo de una CxC incobrable (§11).

Exige ``FINANZAS.castigo.autorizar`` (capa de comandos) y motivo. El saldo va a
la cuenta de cuentas incobrables del perfil SALE; la CxC queda WRITTEN_OFF con
quién, cuándo y por qué. No se borra nada.

    Dr Cuentas incobrables / Cr Clientes
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance._support import require_profile
from backend.domain.finance.enums import AuditAction, JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError, ReceivableNotFoundError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class WriteOffReceivableUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, receivable_id: str, reason: str, write_off_date: date,
                operation_id: str, authorized_by: str) -> str:
        if not (reason or "").strip():
            raise FinanceDomainError("El castigo exige el motivo")
        with FinanceUnitOfWork(connection) as uow:
            receivable = uow.receivables.get(receivable_id)
            if receivable is None:
                raise ReceivableNotFoundError("La cuenta por cobrar no existe")
            existing = uow.journal_entries.find_by_posting_reference(
                "finance", receivable.id, PostingPurpose.RECEIVABLE_WRITE_OFF)
            if existing is not None:
                return existing.id
            before = {"status": receivable.status.value,
                      "outstanding": receivable.outstanding_amount.to_string()}
            amount = receivable.write_off(reason, authorized_by)
            profile = require_profile(uow, "SALE", write_off_date,
                                      branch_id=receivable.branch_id)
            entry = self._engine.post(
                uow, JournalType.ADJUSTMENTS, write_off_date,
                f"Castigo de CxC: {reason.strip()}",
                PostingReference("finance", receivable.id, PostingPurpose.RECEIVABLE_WRITE_OFF,
                                 operation_id),
                [LineSpec(profile.account_for("write_off_expense_account_id"), debit=amount,
                          description="Cuenta incobrable", customer_id=receivable.customer_id),
                 LineSpec(profile.account_for("receivable_account_id"), credit=amount,
                          description="Baja de la CxC castigada",
                          customer_id=receivable.customer_id)],
                currency_code=amount.currency_code, branch_id=receivable.branch_id,
                created_by=authorized_by)
            uow.receivables.update(receivable)
            document = uow.financial_documents.get(receivable.financial_document_id)
            if document is not None:
                document.apply_settlement(amount)
                uow.financial_documents.update(document)
            uow.audit(AuditAction.RECEIVABLE_WRITTEN_OFF, entity_type="receivable",
                      entity_id=receivable.id, operation_id=operation_id,
                      user_id=authorized_by, before=before,
                      after={"status": receivable.status.value, "journal_entry_id": entry.id},
                      reason=reason, branch_id=receivable.branch_id)
            return entry.id
