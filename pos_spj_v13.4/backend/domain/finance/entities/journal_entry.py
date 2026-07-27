"""JournalEntry aggregate — double-entry accounting entry with lines.

Invariants:
- Every line carries exactly one positive side (debit XOR credit).
- A VALIDATED/POSTED entry satisfies total debits == total credits.
- A POSTED entry is immutable; corrections happen only via reversal entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.enums import JournalEntryStatus, PostingPurpose
from backend.domain.finance.exceptions import (
    EmptyEntryError,
    ImmutableEntryError,
    InvalidEntryStateError,
    UnbalancedEntryError,
)
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class JournalLine:
    id: str
    journal_entry_id: str
    account_id: str
    description: str
    debit: Money
    credit: Money
    cost_center_id: str | None = None
    profit_center_id: str | None = None
    branch_id: str | None = None
    line_index: int = 0

    @classmethod
    def debit_line(cls, journal_entry_id: str, account_id: str, amount: Money,
                   description: str = "", **kwargs) -> "JournalLine":
        return cls(
            id=new_uuid(), journal_entry_id=journal_entry_id, account_id=account_id,
            description=description, debit=amount, credit=Money.zero(amount.currency_code),
            **kwargs,
        )

    @classmethod
    def credit_line(cls, journal_entry_id: str, account_id: str, amount: Money,
                    description: str = "", **kwargs) -> "JournalLine":
        return cls(
            id=new_uuid(), journal_entry_id=journal_entry_id, account_id=account_id,
            description=description, debit=Money.zero(amount.currency_code), credit=amount,
            **kwargs,
        )

    def validate(self) -> None:
        if self.debit.is_negative() or self.credit.is_negative():
            raise EmptyEntryError("Journal line amounts must not be negative")
        if self.debit.is_zero() == self.credit.is_zero():
            raise EmptyEntryError(
                "Each journal line must have exactly one positive side (debit XOR credit)"
            )
        if not self.account_id:
            raise EmptyEntryError("Journal line requires an account_id")


@dataclass(slots=True)
class JournalEntry:
    id: str
    journal_id: str
    entry_number: str
    entry_date: date
    fiscal_period_id: str
    description: str
    currency_code: str
    posting_reference: PostingReference
    branch_id: str | None = None
    status: JournalEntryStatus = JournalEntryStatus.DRAFT
    reversal_of_entry_id: str | None = None
    reversed_by_entry_id: str | None = None
    posted_at: str | None = None
    created_by: str | None = None
    lines: list[JournalLine] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # ── construction ──────────────────────────────────────────────────────
    @classmethod
    def create(
        cls,
        journal_id: str,
        entry_number: str,
        entry_date: date,
        fiscal_period_id: str,
        description: str,
        posting_reference: PostingReference,
        *,
        currency_code: str = "MXN",
        branch_id: str | None = None,
        created_by: str | None = None,
        reversal_of_entry_id: str | None = None,
    ) -> "JournalEntry":
        return cls(
            id=new_uuid(),
            journal_id=journal_id,
            entry_number=entry_number,
            entry_date=entry_date,
            fiscal_period_id=fiscal_period_id,
            description=description,
            currency_code=currency_code,
            posting_reference=posting_reference,
            branch_id=branch_id,
            created_by=created_by,
            reversal_of_entry_id=reversal_of_entry_id,
        )

    def add_debit(self, account_id: str, amount: Money, description: str = "", **kwargs) -> JournalLine:
        self._assert_mutable()
        line = JournalLine.debit_line(self.id, account_id, amount, description,
                                      line_index=len(self.lines), **kwargs)
        self.lines.append(line)
        return line

    def add_credit(self, account_id: str, amount: Money, description: str = "", **kwargs) -> JournalLine:
        self._assert_mutable()
        line = JournalLine.credit_line(self.id, account_id, amount, description,
                                       line_index=len(self.lines), **kwargs)
        self.lines.append(line)
        return line

    # ── totals ────────────────────────────────────────────────────────────
    def total_debits(self) -> Money:
        total = Money.zero(self.currency_code)
        for line in self.lines:
            total = total.add(line.debit)
        return total

    def total_credits(self) -> Money:
        total = Money.zero(self.currency_code)
        for line in self.lines:
            total = total.add(line.credit)
        return total

    def is_balanced(self) -> bool:
        return self.total_debits().amount == self.total_credits().amount

    # ── lifecycle ─────────────────────────────────────────────────────────
    def validate(self) -> None:
        """DRAFT → VALIDATED. Enforces line integrity and double-entry balance."""
        if self.status is not JournalEntryStatus.DRAFT:
            raise InvalidEntryStateError(f"Cannot validate entry in status {self.status.value}")
        if not self.lines:
            raise EmptyEntryError("A journal entry requires at least two lines")
        for line in self.lines:
            line.validate()
        if len(self.lines) < 2:
            raise EmptyEntryError("A journal entry requires at least two lines")
        if not self.is_balanced():
            raise UnbalancedEntryError(
                f"Entry {self.entry_number} is unbalanced: "
                f"debits={self.total_debits().to_string()} credits={self.total_credits().to_string()}"
            )
        self.status = JournalEntryStatus.VALIDATED
        self.updated_at = _utcnow()

    def mark_posted(self) -> None:
        """VALIDATED → POSTED. Period control is enforced by the posting service."""
        if self.status is not JournalEntryStatus.VALIDATED:
            raise InvalidEntryStateError(f"Cannot post entry in status {self.status.value}")
        if not self.is_balanced():
            raise UnbalancedEntryError(f"Entry {self.entry_number} became unbalanced before posting")
        self.status = JournalEntryStatus.POSTED
        self.posted_at = _utcnow()
        self.updated_at = self.posted_at

    def mark_reversed(self, reversal_entry_id: str) -> None:
        """POSTED → REVERSED. The original entry is never edited or deleted."""
        if self.status is not JournalEntryStatus.POSTED:
            raise InvalidEntryStateError(f"Only POSTED entries can be reversed (status={self.status.value})")
        self.status = JournalEntryStatus.REVERSED
        self.reversed_by_entry_id = reversal_entry_id
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        """DRAFT/VALIDATED → CANCELLED. Published entries can never be cancelled."""
        if self.status not in (JournalEntryStatus.DRAFT, JournalEntryStatus.VALIDATED):
            raise ImmutableEntryError(
                f"Entry {self.entry_number} is {self.status.value}; use a reversal instead"
            )
        self.status = JournalEntryStatus.CANCELLED
        self.updated_at = _utcnow()

    # ── guards ────────────────────────────────────────────────────────────
    def _assert_mutable(self) -> None:
        if self.status not in (JournalEntryStatus.DRAFT,):
            raise ImmutableEntryError(
                f"Entry {self.entry_number} is {self.status.value} and cannot be modified; "
                "corrections require a reversal entry"
            )
