"""Balanced entry policy — total debits must equal total credits."""

from __future__ import annotations

from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.exceptions import EmptyEntryError, UnbalancedEntryError


class BalancedEntryPolicy:
    """Every postable entry must satisfy Σ(debits) == Σ(credits) with ≥ 2 lines."""

    def enforce(self, entry: JournalEntry) -> None:
        if len(entry.lines) < 2:
            raise EmptyEntryError(
                f"Entry {entry.entry_number} needs at least two lines (has {len(entry.lines)})"
            )
        for line in entry.lines:
            line.validate()
        debits = entry.total_debits()
        credits = entry.total_credits()
        if debits.amount != credits.amount:
            raise UnbalancedEntryError(
                f"Entry {entry.entry_number} unbalanced: debits={debits.to_string()} "
                f"credits={credits.to_string()}"
            )
