"""Reversión de asientos — caso de uso de aplicación (auditoría d9f2bca F26).

La coordinación vivía en la composición del frontend (``finance_routes``):
abría la unidad de trabajo, buscaba el asiento y llamaba al motor sin actor ni
permiso. Aquí queda como caso de uso; la autorización la exige
``FinanceCommandService`` y el actor viaja al asiento de reversión.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class ReverseJournalEntryUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, journal_entry_id: str, reason: str, reversal_date: date,
                operation_id: str, reversed_by: str | None = None) -> JournalEntry:
        if not (reason or "").strip():
            raise FinanceDomainError("Revertir un asiento exige el motivo")
        with FinanceUnitOfWork(connection) as uow:
            entry = uow.journal_entries.get(journal_entry_id)
            if entry is None:
                raise FinanceDomainError("El asiento no existe")
            return self._engine.reverse(uow, entry, reversal_date, reason.strip(), operation_id,
                                        created_by=reversed_by)
