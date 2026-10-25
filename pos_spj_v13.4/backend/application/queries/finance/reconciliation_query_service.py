"""ReconciliationQueryService — conciliaciones y partidas de estados de cuenta (§15)."""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
)


class ReconciliationQueryService(FinanceQueryServiceBase):
    def list_reconciliations(self, *, status: str | None = None) -> list[dict]:
        sql = ("SELECT r.id, r.treasury_account_id, ta.name AS treasury_account_name,"
               " r.bank_statement_id, bs.statement_date, r.status, r.completed_by,"
               " r.completed_at, r.difference_reason, r.reverted_by, r.revert_reason,"
               " (SELECT COUNT(*) FROM bank_statement_lines l WHERE l.bank_statement_id ="
               "  r.bank_statement_id AND l.status IN ('UNMATCHED','SUGGESTED',"
               "  'ADJUSTMENT_REQUIRED')) AS pending_lines"
               " FROM reconciliations r JOIN treasury_accounts ta ON ta.id = r.treasury_account_id"
               " JOIN bank_statements bs ON bs.id = r.bank_statement_id")
        params: tuple = ()
        if status:
            sql += " WHERE r.status = ?"
            params = (status,)
        return self._query(sql + " ORDER BY r.created_at DESC LIMIT 200", params)

    def statement_lines(self, bank_statement_id: str, *, open_only: bool = False) -> list[dict]:
        sql = ("SELECT id, transaction_date, description, amount, external_reference, status,"
               " matched_journal_line_id, suggested_journal_line_id, suggestion_score,"
               " ignored_reason, adjustment_journal_entry_id FROM bank_statement_lines"
               " WHERE bank_statement_id = ?")
        if open_only:
            sql += " AND status IN ('UNMATCHED','SUGGESTED','ADJUSTMENT_REQUIRED')"
        return self._query(sql + " ORDER BY line_index", (bank_statement_id,))

    def unmatched_statement_lines(self, bank_statement_id: str) -> list[dict]:
        return self.statement_lines(bank_statement_id, open_only=True)

    def statements_without_reconciliation(self) -> list[dict]:
        return self._query(
            "SELECT bs.id, bs.statement_date, ta.name AS treasury_account_name"
            " FROM bank_statements bs JOIN treasury_accounts ta ON ta.id = bs.treasury_account_id"
            " WHERE bs.id NOT IN (SELECT bank_statement_id FROM reconciliations"
            "                     WHERE status <> 'REVERTED') ORDER BY bs.statement_date")
