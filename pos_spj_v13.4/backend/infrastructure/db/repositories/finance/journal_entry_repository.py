"""JournalEntry repository — entries with lines, idempotency lookups."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.journal_entry import JournalEntry, JournalLine
from backend.domain.finance.enums import JournalEntryStatus, PostingPurpose
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_ENTRY_COLUMNS = (
    "id, journal_id, entry_number, entry_date, fiscal_period_id, description,"
    " currency_code, status, source_module, source_document_id, posting_purpose,"
    " operation_id, branch_id, reversal_of_entry_id, reversed_by_entry_id,"
    " posted_at, created_by, created_at, updated_at"
)
_LINE_COLUMNS = (
    "id, journal_entry_id, account_id, description, debit_amount, credit_amount,"
    " currency_code, cost_center_id, profit_center_id, branch_id, line_index"
)


def _line_to_entity(row: dict) -> JournalLine:
    currency = row["currency_code"]
    return JournalLine(
        id=row["id"],
        journal_entry_id=row["journal_entry_id"],
        account_id=row["account_id"],
        description=row["description"],
        debit=Money.from_string(row["debit_amount"], currency),
        credit=Money.from_string(row["credit_amount"], currency),
        cost_center_id=row["cost_center_id"],
        profit_center_id=row["profit_center_id"],
        branch_id=row["branch_id"],
        line_index=row["line_index"],
    )


class JournalEntryRepository(FinanceRepositoryBase):
    def save(self, entry: JournalEntry) -> None:
        self._execute(
            f"INSERT INTO journal_entries ({_ENTRY_COLUMNS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (entry.id, entry.journal_id, entry.entry_number, entry.entry_date.isoformat(),
             entry.fiscal_period_id, entry.description, entry.currency_code,
             entry.status.value, entry.posting_reference.source_module,
             entry.posting_reference.source_document_id,
             entry.posting_reference.posting_purpose.value,
             entry.posting_reference.operation_id, entry.branch_id,
             entry.reversal_of_entry_id, entry.reversed_by_entry_id,
             entry.posted_at, entry.created_by, entry.created_at, entry.updated_at),
        )
        for line in entry.lines:
            self._execute(
                f"INSERT INTO journal_lines ({_LINE_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (line.id, line.journal_entry_id, line.account_id, line.description,
                 line.debit.to_string(), line.credit.to_string(),
                 entry.currency_code, line.cost_center_id, line.profit_center_id,
                 line.branch_id, line.line_index),
            )

    def update_status(self, entry: JournalEntry) -> None:
        self._execute(
            "UPDATE journal_entries SET status=?, posted_at=?, reversed_by_entry_id=?, updated_at=?"
            " WHERE id=?",
            (entry.status.value, entry.posted_at, entry.reversed_by_entry_id,
             entry.updated_at, entry.id),
        )

    def get(self, entry_id: str) -> JournalEntry | None:
        row = self._query_one(
            f"SELECT {_ENTRY_COLUMNS} FROM journal_entries WHERE id=?", (entry_id,)
        )
        return self._hydrate(row) if row else None

    def find_by_posting_reference(
        self, source_module: str, source_document_id: str, posting_purpose: PostingPurpose,
    ) -> JournalEntry | None:
        row = self._query_one(
            f"SELECT {_ENTRY_COLUMNS} FROM journal_entries"
            " WHERE source_module=? AND source_document_id=? AND posting_purpose=?",
            (source_module, source_document_id, posting_purpose.value),
        )
        return self._hydrate(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> JournalEntry | None:
        row = self._query_one(
            f"SELECT {_ENTRY_COLUMNS} FROM journal_entries WHERE operation_id=?",
            (operation_id,),
        )
        return self._hydrate(row) if row else None

    def get_posted_line(self, journal_line_id: str) -> dict | None:
        """One journal line of a POSTED entry (read-model for reconciliation)."""
        return self._query_one(
            "SELECT jl.id, jl.debit_amount, jl.credit_amount, jl.currency_code"
            " FROM journal_lines jl JOIN journal_entries je ON je.id=jl.journal_entry_id"
            " WHERE jl.id=? AND je.status='POSTED'",
            (journal_line_id,),
        )

    def exists_unbalanced(self) -> bool:
        row = self._query_one(
            "SELECT COUNT(*) AS unbalanced FROM ("
            "  SELECT journal_entry_id FROM journal_lines"
            "  GROUP BY journal_entry_id"
            "  HAVING SUM(CAST(debit_amount AS NUMERIC)) <> SUM(CAST(credit_amount AS NUMERIC))"
            ")"
        )
        return bool(row and row["unbalanced"])

    def _hydrate(self, row: dict) -> JournalEntry:
        lines = [
            _line_to_entity(line_row)
            for line_row in self._query(
                f"SELECT {_LINE_COLUMNS} FROM journal_lines"
                " WHERE journal_entry_id=? ORDER BY line_index",
                (row["id"],),
            )
        ]
        return JournalEntry(
            id=row["id"],
            journal_id=row["journal_id"],
            entry_number=row["entry_number"],
            entry_date=date.fromisoformat(row["entry_date"]),
            fiscal_period_id=row["fiscal_period_id"],
            description=row["description"],
            currency_code=row["currency_code"],
            posting_reference=PostingReference(
                source_module=row["source_module"],
                source_document_id=row["source_document_id"],
                posting_purpose=PostingPurpose(row["posting_purpose"]),
                operation_id=row["operation_id"],
            ),
            branch_id=row["branch_id"],
            status=JournalEntryStatus(row["status"]),
            reversal_of_entry_id=row["reversal_of_entry_id"],
            reversed_by_entry_id=row["reversed_by_entry_id"],
            posted_at=row["posted_at"],
            created_by=row["created_by"],
            lines=lines,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
