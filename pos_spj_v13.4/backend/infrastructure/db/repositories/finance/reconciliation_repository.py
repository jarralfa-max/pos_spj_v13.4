"""Reconciliation repository."""

from __future__ import annotations

from backend.domain.finance.entities.reconciliation import Reconciliation, ReconciliationMatch
from backend.domain.finance.enums import ReconciliationStatus
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, treasury_account_id, bank_statement_id, status, completed_by,"
            " completed_at, reverted_by, revert_reason, operation_id, created_at, updated_at")
_MATCH_COLUMNS = ("id, reconciliation_id, bank_statement_line_id, journal_line_id,"
                  " matched_by, matched_at")


class ReconciliationRepository(FinanceRepositoryBase):
    def save(self, reconciliation: Reconciliation) -> None:
        self._execute(
            f"INSERT INTO reconciliations ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (reconciliation.id, reconciliation.treasury_account_id,
             reconciliation.bank_statement_id, reconciliation.status.value,
             reconciliation.completed_by, reconciliation.completed_at,
             reconciliation.reverted_by, reconciliation.revert_reason,
             reconciliation.operation_id, reconciliation.created_at,
             reconciliation.updated_at),
        )
        self._save_new_matches(reconciliation)

    def update(self, reconciliation: Reconciliation) -> None:
        self._execute(
            "UPDATE reconciliations SET status=?, completed_by=?, completed_at=?,"
            " reverted_by=?, revert_reason=?, updated_at=? WHERE id=?",
            (reconciliation.status.value, reconciliation.completed_by,
             reconciliation.completed_at, reconciliation.reverted_by,
             reconciliation.revert_reason, reconciliation.updated_at, reconciliation.id),
        )
        self._save_new_matches(reconciliation)

    def _save_new_matches(self, reconciliation: Reconciliation) -> None:
        existing = {
            row["id"] for row in self._query(
                "SELECT id FROM reconciliation_matches WHERE reconciliation_id=?",
                (reconciliation.id,),
            )
        }
        for match in reconciliation.matches:
            if match.id not in existing:
                self._execute(
                    f"INSERT INTO reconciliation_matches ({_MATCH_COLUMNS}) VALUES (?,?,?,?,?,?)",
                    (match.id, match.reconciliation_id, match.bank_statement_line_id,
                     match.journal_line_id, match.matched_by, match.matched_at),
                )

    def get(self, reconciliation_id: str) -> Reconciliation | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM reconciliations WHERE id=?", (reconciliation_id,)
        )
        return self._hydrate(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Reconciliation | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM reconciliations WHERE operation_id=?", (operation_id,)
        )
        return self._hydrate(row) if row else None

    def list_open(self) -> list[Reconciliation]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM reconciliations WHERE status IN ('OPEN','IN_PROGRESS')"
        )
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: dict) -> Reconciliation:
        reconciliation = Reconciliation(
            id=row["id"], treasury_account_id=row["treasury_account_id"],
            bank_statement_id=row["bank_statement_id"],
            operation_id=row["operation_id"],
            status=ReconciliationStatus(row["status"]),
            completed_by=row["completed_by"], completed_at=row["completed_at"],
            reverted_by=row["reverted_by"], revert_reason=row["revert_reason"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
        for match_row in self._query(
            f"SELECT {_MATCH_COLUMNS} FROM reconciliation_matches WHERE reconciliation_id=?",
            (row["id"],),
        ):
            reconciliation.matches.append(ReconciliationMatch(
                id=match_row["id"], reconciliation_id=match_row["reconciliation_id"],
                bank_statement_line_id=match_row["bank_statement_line_id"],
                journal_line_id=match_row["journal_line_id"],
                matched_by=match_row["matched_by"], matched_at=match_row["matched_at"],
            ))
        return reconciliation
