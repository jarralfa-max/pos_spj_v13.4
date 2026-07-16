"""Reversal policy — corrections only via reversal entries, never edits."""

from __future__ import annotations

from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.enums import JournalEntryStatus
from backend.domain.finance.exceptions import ReversalError


class ReversalPolicy:
    def enforce(self, original: JournalEntry, *, reason: str) -> None:
        if original.status is not JournalEntryStatus.POSTED:
            raise ReversalError(
                f"Only POSTED entries can be reversed; {original.entry_number} is "
                f"{original.status.value}"
            )
        if original.reversed_by_entry_id:
            raise ReversalError(
                f"Entry {original.entry_number} was already reversed by "
                f"{original.reversed_by_entry_id}; double reversal is forbidden"
            )
        if not reason or not reason.strip():
            raise ReversalError("A reversal requires an explicit reason")
