"""Reconciliation entities — matching statement lines against ledger movements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import ReconciliationStatus
from backend.domain.finance.exceptions import (
    ReconciliationError,
    TransactionAlreadyReconciledError,
)
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
    #: Un match revertido se conserva como historia pero deja de ser una
    #: asignación vigente (auditoría F08).
    active: bool = True
    reverted_at: str | None = None
    reverted_by: str | None = None
    revert_reason: str | None = None

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
    #: Diferencia aceptada al completar con partidas sin conciliar (F08).
    difference_reason: str | None = None
    matches: list[ReconciliationMatch] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, treasury_account_id: str, bank_statement_id: str, operation_id: str) -> "Reconciliation":
        return cls(
            id=new_uuid(), treasury_account_id=treasury_account_id,
            bank_statement_id=bank_statement_id, operation_id=operation_id,
        )

    def active_matches(self) -> list[ReconciliationMatch]:
        return [match for match in self.matches if match.active]

    def add_match(self, bank_statement_line_id: str, journal_line_id: str, matched_by: str) -> ReconciliationMatch:
        if self.status in (ReconciliationStatus.COMPLETED, ReconciliationStatus.REVERTED):
            raise ReconciliationError(
                f"Cannot add matches to a {self.status.value.lower()} reconciliation")
        for match in self.active_matches():
            if match.bank_statement_line_id == bank_statement_line_id:
                raise TransactionAlreadyReconciledError(
                    "La partida del estado ya está conciliada")
            if match.journal_line_id == journal_line_id:
                raise TransactionAlreadyReconciledError(
                    "El movimiento del mayor ya está conciliado")
        match = ReconciliationMatch.create(self.id, bank_statement_line_id, journal_line_id, matched_by)
        self.matches.append(match)
        self.status = ReconciliationStatus.IN_PROGRESS
        self.updated_at = _utcnow()
        return match

    def complete(self, completed_by: str, *, unmatched_lines: int = 0,
                 difference_reason: str | None = None) -> None:
        """COMPLETED acredita conciliación total (auditoría F08): con partidas
        del estado sin conciliar sólo se completa declarando el motivo de la
        diferencia aceptada (quien llama exige el permiso para aceptarla)."""
        if self.status not in (ReconciliationStatus.OPEN, ReconciliationStatus.IN_PROGRESS):
            raise ReconciliationError(f"Cannot complete reconciliation in status {self.status.value}")
        if not self.active_matches() and not (difference_reason or "").strip():
            raise ReconciliationError("Cannot complete a reconciliation without matches")
        if unmatched_lines and not (difference_reason or "").strip():
            raise ReconciliationError(
                f"Quedan {unmatched_lines} partidas del estado sin conciliar; "
                "concílielas o declare el motivo de la diferencia")
        self.difference_reason = (difference_reason or "").strip() or None
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
        now = _utcnow()
        # Revertir inactiva las asignaciones: las líneas vuelven a estar
        # disponibles para conciliarse, y el historial (quién, cuándo) queda.
        for match in self.active_matches():
            match.active = False
            match.reverted_at = now
            match.reverted_by = reverted_by
            match.revert_reason = reason.strip()
        self.status = ReconciliationStatus.REVERTED
        self.reverted_by = reverted_by
        self.revert_reason = reason.strip()
        self.updated_at = now
