"""Reversal policy — corrections only via reversal entries, never edits."""

from __future__ import annotations

from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.enums import JournalEntryStatus
from backend.domain.finance.exceptions import JournalEntryAlreadyReversedError, ReversalError


class ReversalPolicy:
    def enforce(self, original: JournalEntry, *, reason: str) -> None:
        if original.reversed_by_entry_id or original.status is JournalEntryStatus.REVERSED:
            raise JournalEntryAlreadyReversedError(
                f"El asiento {original.entry_number} ya fue revertido; "
                "un segundo reverso está prohibido")
        if original.status is not JournalEntryStatus.POSTED:
            raise ReversalError(
                f"Sólo se revierte un asiento contabilizado; {original.entry_number} está "
                f"{original.status.value}")
        if not reason or not reason.strip():
            raise ReversalError("Revertir un asiento exige el motivo")
