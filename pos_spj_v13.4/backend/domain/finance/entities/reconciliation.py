"""Reconciliation entities — matching statement lines against ledger movements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import ReconciliationStatus
from backend.domain.finance.exceptions import ReconciliationError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ReconciliationMatch:
    id: str
    reconciliation_id: str
    bank_statement_line_id: str
    journal_line_id: str
    matched_by: str
    matched_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, reconciliation_id: str, bank_statement_line_id: str,
               journal_line_id: str, matched_by: str) -> "ReconciliationMatch":
        return cls(
            id=new_uuid(), reconciliation_id=reconciliation_id,
            bank_statement_line_id=bank_statement_line_id,
            journal_line_id=journal_line_id, matched_by=matched_by,
        )


@dataclass(slots=True)
class Reconciliation:
    id: str
    treasury_account_id: str
    bank_statement_id: str
    operation_id: str
    status: ReconciliationStatus = ReconciliationStatus.OPEN
    completed_by: str | None = None
    completed_at: str | None = None
    reverted_by: str | None = None
    revert_reason: str | None = None
    matches: list[ReconciliationMatch] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, treasury_account_id: str, bank_statement_id: str, operation_id: str) -> "Reconciliation":
        return cls(
            id=new_uuid(), treasury_account_id=treasury_account_id,
            bank_statement_id=bank_statement_id, operation_id=operation_id,
        )

    def add_match(self, bank_statement_line_id: str, journal_line_id: str, matched_by: str) -> ReconciliationMatch:
        if self.status is ReconciliationStatus.COMPLETED:
            raise ReconciliationError("Cannot add matches to a completed reconciliation")
        for match in self.matches:
            if match.bank_statement_line_id == bank_statement_line_id:
                raise ReconciliationError("Statement line is already matched")
            if match.journal_line_id == journal_line_id:
                raise ReconciliationError("Journal line is already matched")
        match = ReconciliationMatch.create(self.id, bank_statement_line_id, journal_line_id, matched_by)
        self.matches.append(match)
        self.status = ReconciliationStatus.IN_PROGRESS
        self.updated_at = _utcnow()
        return match

    def complete(self, completed_by: str) -> None:
        if self.status not in (ReconciliationStatus.OPEN, ReconciliationStatus.IN_PROGRESS):
            raise ReconciliationError(f"Cannot complete reconciliation in status {self.status.value}")
        if not self.matches:
            raise ReconciliationError("Cannot complete a reconciliation without matches")
        self.status = ReconciliationStatus.COMPLETED
        self.completed_by = completed_by
        self.completed_at = _utcnow()
        self.updated_at = self.completed_at

    def revert(self, reverted_by: str, reason: str) -> None:
        """Undo requires explicit authorization identity and reason."""
        if self.status is not ReconciliationStatus.COMPLETED:
            raise ReconciliationError("Only completed reconciliations can be reverted")
        if not reverted_by or not reason or not reason.strip():
            raise ReconciliationError("Reverting a reconciliation requires user and reason")
        self.status = ReconciliationStatus.REVERTED
        self.reverted_by = reverted_by
        self.revert_reason = reason.strip()
        self.updated_at = _utcnow()
