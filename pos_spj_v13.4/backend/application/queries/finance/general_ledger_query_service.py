"""GeneralLedgerQueryService — POSTED-only ledger reads for UI and BI."""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
)
from backend.domain.finance.enums import AccountType, CashFlowCategory, NormalBalance
from backend.domain.finance.services.financial_statement_builder import AccountBalanceRow
from backend.domain.finance.value_objects.money import Money

_POSTED = "('POSTED','REVERSED')"  # reversed originals stay in the ledger; reversal entries offset them


class GeneralLedgerQueryService(FinanceQueryServiceBase):
    def account_balances(self, *, date_from: str | None = None, date_to: str | None = None,
                         branch_id: str | None = None,
                         currency_code: str = "MXN") -> list[AccountBalanceRow]:
        """Aggregated debit/credit per account from POSTED entries."""
        conditions = [f"je.status IN {_POSTED}"]
        params: list = []
        if date_from:
            conditions.append("je.entry_date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("je.entry_date <= ?")
            params.append(date_to)
        if branch_id:
            conditions.append("je.branch_id = ?")
            params.append(branch_id)
        rows = self._query(
            "SELECT a.id, a.code, a.name, a.account_type, a.normal_balance,"
            " a.cash_flow_category,"
            " COALESCE(SUM(CAST(jl.debit_amount AS NUMERIC)), 0) AS debits,"
            " COALESCE(SUM(CAST(jl.credit_amount AS NUMERIC)), 0) AS credits"
            " FROM accounts a"
            " JOIN journal_lines jl ON jl.account_id = a.id"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}"
            " GROUP BY a.id, a.code, a.name, a.account_type, a.normal_balance,"
            " a.cash_flow_category ORDER BY a.code",
            tuple(params),
        )
        return [
            AccountBalanceRow(
                account_id=row["id"], account_code=row["code"], account_name=row["name"],
                account_type=AccountType(row["account_type"]),
                normal_balance=NormalBalance(row["normal_balance"]),
                total_debits=Money.from_string(str(row["debits"]), currency_code),
                total_credits=Money.from_string(str(row["credits"]), currency_code),
                cash_flow_category=CashFlowCategory(row["cash_flow_category"]),
            )
            for row in rows
        ]

    def ledger_lines(self, account_id: str, *, date_from: str | None = None,
                     date_to: str | None = None, limit: int = 500) -> list[dict]:
        conditions = ["jl.account_id = ?", f"je.status IN {_POSTED}"]
        params: list = [account_id]
        if date_from:
            conditions.append("je.entry_date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("je.entry_date <= ?")
            params.append(date_to)
        params.append(limit)
        return self._query(
            "SELECT je.entry_date, je.entry_number, je.description AS entry_description,"
            " jl.id AS journal_line_id, jl.description, jl.debit_amount, jl.credit_amount,"
            " je.source_module, je.posting_purpose, je.branch_id"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY je.entry_date, je.entry_number LIMIT ?",
            tuple(params),
        )

    def unmatched_treasury_lines(self, ledger_account_id: str, *, limit: int = 500) -> list[dict]:
        """POSTED lines on a treasury mirror account not yet reconciled."""
        return self._query(
            "SELECT jl.id AS journal_line_id, je.entry_date, je.entry_number,"
            " jl.debit_amount, jl.credit_amount, jl.description"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            " WHERE jl.account_id = ? AND je.status = 'POSTED'"
            " AND jl.id NOT IN (SELECT journal_line_id FROM reconciliation_matches)"
            " ORDER BY je.entry_date LIMIT ?",
            (ledger_account_id, limit),
        )
