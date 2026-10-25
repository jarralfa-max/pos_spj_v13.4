"""Reconciliation repository."""

from __future__ import annotations

from backend.domain.finance.entities.reconciliation import Reconciliation, ReconciliationMatch
from backend.domain.finance.enums import ReconciliationStatus
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, treasury_account_id, bank_statement_id, status, completed_by,"
            " completed_at, reverted_by, revert_reason, operation_id, created_at, updated_at,"
            " difference_reason")
_MATCH_COLUMNS = ("id, reconciliation_id, bank_statement_line_id, journal_line_id,"
                  " matched_by, matched_at, active, reverted_at, reverted_by, revert_reason")


class ReconciliationRepository(FinanceRepositoryBase):
    def save(self, reconciliation: Reconciliation) -> None:
        self._execute(
            f"INSERT INTO reconciliations ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (reconciliation.id, reconciliation.treasury_account_id,
             reconciliation.bank_statement_id, reconciliation.status.value,
             reconciliation.completed_by, reconciliation.completed_at,
             reconciliation.reverted_by, reconciliation.revert_reason,
             reconciliation.operation_id, reconciliation.created_at,
             reconciliation.updated_at, reconciliation.difference_reason),
        )
        self._save_new_matches(reconciliation)

    def update(self, reconciliation: Reconciliation) -> None:
        self._execute(
            "UPDATE reconciliations SET status=?, completed_by=?, completed_at=?,"
            " reverted_by=?, revert_reason=?, updated_at=?, difference_reason=? WHERE id=?",
            (reconciliation.status.value, reconciliation.completed_by,
             reconciliation.completed_at, reconciliation.reverted_by,
             reconciliation.revert_reason, reconciliation.updated_at,
             reconciliation.difference_reason, reconciliation.id),
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
                    f"INSERT INTO reconciliation_matches ({_MATCH_COLUMNS})"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (match.id, match.reconciliation_id, match.bank_statement_line_id,
                     match.journal_line_id, match.matched_by, match.matched_at,
                     int(match.active), match.reverted_at, match.reverted_by,
                     match.revert_reason),
                )
            else:
                self._execute(
                    "UPDATE reconciliation_matches SET active=?, reverted_at=?, reverted_by=?,"
                    " revert_reason=? WHERE id=?",
                    (int(match.active), match.reverted_at, match.reverted_by,
                     match.revert_reason, match.id),
                )

    def journal_line_has_active_match(self, journal_line_id: str) -> bool:
        """Unicidad GLOBAL (F07): una línea del mayor consumida por un match
        activo de cualquier conciliación no se reutiliza."""
        return self._query_one(
            "SELECT 1 AS hit FROM reconciliation_matches WHERE journal_line_id=? AND active=1",
            (journal_line_id,)) is not None

    def statement_line_has_active_match(self, bank_statement_line_id: str) -> bool:
        return self._query_one(
            "SELECT 1 AS hit FROM reconciliation_matches"
            " WHERE bank_statement_line_id=? AND active=1",
            (bank_statement_line_id,)) is not None

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

    def list_open(self, *, statement_date_until: str | None = None) -> list[Reconciliation]:
        """Conciliaciones abiertas; con ``statement_date_until`` sólo las de
        estados de cuenta hasta esa fecha (F16: el trabajo de julio no bloquea
        el cierre de junio)."""
        if statement_date_until is None:
            rows = self._query(
                f"SELECT {_COLUMNS} FROM reconciliations WHERE status IN ('OPEN','IN_PROGRESS')"
            )
        else:
            rows = self._query(
                f"SELECT {', '.join('r.' + c.strip() for c in _COLUMNS.split(','))}"
                " FROM reconciliations r JOIN bank_statements bs ON bs.id = r.bank_statement_id"
                " WHERE r.status IN ('OPEN','IN_PROGRESS') AND bs.statement_date <= ?",
                (statement_date_until,),
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
            difference_reason=row["difference_reason"],
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
                active=bool(match_row["active"]), reverted_at=match_row["reverted_at"],
                reverted_by=match_row["reverted_by"], revert_reason=match_row["revert_reason"],
            ))
        return reconciliation

    def eligible_ledger_lines(self, ledger_account_id: str, currency_code: str, *,
                              limit: int = 1000) -> list[dict]:
        """Líneas CONTABILIZADAS de la cuenta espejo, en su moneda, sin match activo."""
        return self._query(
            "SELECT jl.id AS journal_line_id, je.posting_date, je.entry_number,"
            " je.description AS entry_description, jl.description, jl.source_reference,"
            " jl.debit_amount, jl.credit_amount, jl.currency_code"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            " WHERE jl.account_id = ? AND jl.currency_code = ? AND je.status = 'POSTED'"
            " AND jl.id NOT IN (SELECT journal_line_id FROM reconciliation_matches"
            "                   WHERE active = 1)"
            " ORDER BY je.posting_date LIMIT ?", (ledger_account_id, currency_code, limit))
