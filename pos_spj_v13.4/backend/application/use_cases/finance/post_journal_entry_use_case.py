"""PostJournalEntryUseCase — contabiliza un asiento manual validado (§8.3, §9, §28).

- Segregación: con revisión obligatoria (configuración), quien lo capturó no
  lo contabiliza.
- Periodo pre-cerrado: sólo con el permiso de ajuste en periodo cerrado, que
  exige la capa de comandos y aquí llega como ``allow_soft_closed``.
- Recibe su folio definitivo del diario al contabilizarse; desde ese momento
  es inmutable.
"""

from __future__ import annotations

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import AuditAction, JournalEntryStatus
from backend.domain.finance.exceptions import (
    InvalidEntryStateError,
    JournalEntryAlreadyPostedError,
    JournalEntryNotFoundError,
)
from backend.domain.finance.policies.segregation_policy import SegregationPolicy
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class PostJournalEntryUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, journal_entry_id: str, operation_id: str,
                posted_by: str, allow_soft_closed: bool = False):
        with FinanceUnitOfWork(connection) as uow:
            entry = uow.journal_entries.get(journal_entry_id)
            if entry is None:
                raise JournalEntryNotFoundError("El asiento no existe")
            if entry.status in (JournalEntryStatus.POSTED, JournalEntryStatus.REVERSED):
                raise JournalEntryAlreadyPostedError(
                    f"El asiento {entry.entry_number} ya está contabilizado")
            if entry.status is not JournalEntryStatus.VALIDATED:
                raise InvalidEntryStateError(
                    "Valide el asiento antes de contabilizarlo (debe cuadrar)")
            SegregationPolicy(uow.settings).enforce_journal_posting(
                created_by=entry.created_by, posted_by=posted_by)
            draft_number = entry.entry_number
            self._engine.post_existing(uow, entry, posted_by=posted_by,
                                       allow_soft_closed=allow_soft_closed)
            uow.audit(AuditAction.JOURNAL_ENTRY_POSTED, entity_type="journal_entry",
                      entity_id=entry.id, operation_id=operation_id, user_id=posted_by,
                      before={"entry_number": draft_number, "status": "VALIDATED"},
                      after={"entry_number": entry.entry_number, "status": entry.status.value,
                             "soft_closed_adjustment": allow_soft_closed},
                      branch_id=entry.branch_id)
            return entry
