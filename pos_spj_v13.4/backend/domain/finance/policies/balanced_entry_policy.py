"""Balanced entry policy — total debits must equal total credits."""

from __future__ import annotations

from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.exceptions import EmptyEntryError, UnbalancedJournalEntryError


class BalancedEntryPolicy:
    """Every postable entry satisfies Σ(debits) == Σ(credits) with ≥ 2 lines,
    in base currency and in the operation currency."""

    def enforce(self, entry: JournalEntry) -> None:
        if len(entry.lines) < 2:
            raise EmptyEntryError(
                f"El asiento {entry.entry_number} requiere al menos dos líneas "
                f"(tiene {len(entry.lines)})")
        for line in entry.lines:
            line.validate()
        if entry.total_debits().amount != entry.total_credits().amount:
            raise UnbalancedJournalEntryError(
                f"El asiento {entry.entry_number} no cuadra: débitos "
                f"{entry.total_debits().to_string()} ≠ créditos "
                f"{entry.total_credits().to_string()}")
        if entry.base_total_debits().amount != entry.base_total_credits().amount:
            raise UnbalancedJournalEntryError(
                f"El asiento {entry.entry_number} no cuadra en moneda base: débitos "
                f"{entry.base_total_debits().to_string()} ≠ créditos "
                f"{entry.base_total_credits().to_string()}")
