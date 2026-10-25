"""ReverseJournalEntryUseCase — toda corrección de un asiento contabilizado es un reverso.

El original nunca se edita ni se borra; el reverso queda ligado a él, con
motivo y actor. Un segundo reverso del mismo asiento se rechaza.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import JournalEntryNotFoundError, ReversalError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class ReverseJournalEntryUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, journal_entry_id: str, reason: str, reversal_date: date,
                operation_id: str, reversed_by: str | None = None) -> JournalEntry:
        if not (reason or "").strip():
            raise ReversalError("Revertir un asiento exige el motivo")
        with FinanceUnitOfWork(connection) as uow:
            entry = uow.journal_entries.get(journal_entry_id)
            if entry is None:
                raise JournalEntryNotFoundError("El asiento no existe")
            reversal = self._engine.reverse(uow, entry, reversal_date, reason.strip(),
                                            operation_id, created_by=reversed_by)
            uow.audit(AuditAction.JOURNAL_ENTRY_REVERSED, entity_type="journal_entry",
                      entity_id=entry.id, operation_id=operation_id, user_id=reversed_by,
                      before={"status": "POSTED"},
                      after={"status": entry.status.value,
                             "reversal_entry_id": reversal.id,
                             "reversal_number": reversal.entry_number},
                      reason=reason, branch_id=entry.branch_id)
            return reversal
