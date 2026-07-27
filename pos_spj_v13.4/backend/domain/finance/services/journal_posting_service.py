"""JournalPostingService — the only domain path to build, post and reverse entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.policies.balanced_entry_policy import BalancedEntryPolicy
from backend.domain.finance.policies.posting_period_policy import PostingPeriodPolicy
from backend.domain.finance.policies.reversal_policy import ReversalPolicy
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference


@dataclass(frozen=True, slots=True)
class LineSpec:
    """Declarative journal line: exactly one of debit/credit must be positive."""

    account_id: str
    debit: Money | None = None
    credit: Money | None = None
    description: str = ""
    cost_center_id: str | None = None
    profit_center_id: str | None = None
    branch_id: str | None = None


class JournalPostingService:
    def __init__(self) -> None:
        self._balanced = BalancedEntryPolicy()
        self._period_policy = PostingPeriodPolicy()
        self._reversal_policy = ReversalPolicy()

    def build_entry(
        self,
        journal_id: str,
        entry_number: str,
        entry_date: date,
        fiscal_period: FiscalPeriod,
        description: str,
        posting_reference: PostingReference,
        line_specs: list[LineSpec],
        *,
        currency_code: str = "MXN",
        branch_id: str | None = None,
        created_by: str | None = None,
        reversal_of_entry_id: str | None = None,
    ) -> JournalEntry:
        """Create a VALIDATED entry (balanced, period known). Not yet posted."""
        entry = JournalEntry.create(
            journal_id=journal_id,
            entry_number=entry_number,
            entry_date=entry_date,
            fiscal_period_id=fiscal_period.id,
            description=description,
            posting_reference=posting_reference,
            currency_code=currency_code,
            branch_id=branch_id,
            created_by=created_by,
            reversal_of_entry_id=reversal_of_entry_id,
        )
        for spec in line_specs:
            kwargs = dict(cost_center_id=spec.cost_center_id,
                          profit_center_id=spec.profit_center_id,
                          branch_id=spec.branch_id)
            if spec.debit is not None and spec.debit.is_positive():
                entry.add_debit(spec.account_id, spec.debit, spec.description, **kwargs)
            if spec.credit is not None and spec.credit.is_positive():
                entry.add_credit(spec.account_id, spec.credit, spec.description, **kwargs)
        self._balanced.enforce(entry)
        entry.validate()
        return entry

    def post(self, entry: JournalEntry, fiscal_period: FiscalPeriod) -> None:
        """VALIDATED → POSTED under period control. POSTED entries are immutable."""
        self._period_policy.enforce(fiscal_period, entry.entry_date)
        entry.mark_posted()

    def build_reversal(
        self,
        original: JournalEntry,
        reversal_entry_number: str,
        reversal_date: date,
        fiscal_period: FiscalPeriod,
        reason: str,
        posting_reference: PostingReference,
        *,
        created_by: str | None = None,
    ) -> JournalEntry:
        """Build the mirror entry of a POSTED original. The original is never edited."""
        self._reversal_policy.enforce(original, reason=reason)
        reversal = JournalEntry.create(
            journal_id=original.journal_id,
            entry_number=reversal_entry_number,
            entry_date=reversal_date,
            fiscal_period_id=fiscal_period.id,
            description=f"REVERSO de {original.entry_number}: {reason}",
            posting_reference=posting_reference,
            currency_code=original.currency_code,
            branch_id=original.branch_id,
            created_by=created_by,
            reversal_of_entry_id=original.id,
        )
        for line in original.lines:
            if line.debit.is_positive():
                reversal.add_credit(line.account_id, line.debit, line.description,
                                    cost_center_id=line.cost_center_id,
                                    profit_center_id=line.profit_center_id,
                                    branch_id=line.branch_id)
            else:
                reversal.add_debit(line.account_id, line.credit, line.description,
                                   cost_center_id=line.cost_center_id,
                                   profit_center_id=line.profit_center_id,
                                   branch_id=line.branch_id)
        self._balanced.enforce(reversal)
        reversal.validate()
        return reversal

    def post_reversal(self, original: JournalEntry, reversal: JournalEntry,
                      fiscal_period: FiscalPeriod) -> None:
        """Post the reversal and mark the original as REVERSED, atomically in domain terms."""
        self.post(reversal, fiscal_period)
        original.mark_reversed(reversal.id)
