"""AccountQueryService — plan de cuentas jerárquico (§8.1)."""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    POSTED,
    FinanceQueryServiceBase,
)


class AccountQueryService(FinanceQueryServiceBase):
    def chart_of_accounts(self) -> list[dict]:
        """Cuentas con su nivel en el árbol, su padre y si ya tienen movimientos."""
        rows = self._query(
            "SELECT a.id, a.code, a.name, a.account_type, a.normal_balance, a.posting_allowed,"
            " a.reconciliation_required, a.cash_flow_category, a.active, a.parent_account_id,"
            " p.code AS parent_code,"
            " EXISTS(SELECT 1 FROM journal_lines jl JOIN journal_entries je"
            f"        ON je.id = jl.journal_entry_id WHERE jl.account_id = a.id"
            f"        AND je.status IN {POSTED}) AS has_movements"
            " FROM accounts a LEFT JOIN accounts p ON p.id = a.parent_account_id"
            " ORDER BY a.code")
        by_id = {row["id"]: row for row in rows}
        for row in rows:
            level, parent = 0, row["parent_account_id"]
            while parent and parent in by_id and level < 10:
                level += 1
                parent = by_id[parent]["parent_account_id"]
            row["level"] = level
            row["has_movements"] = bool(row["has_movements"])
        return rows

    def postable_accounts(self, *, account_types: tuple[str, ...] = ()) -> list[dict]:
        sql = ("SELECT id, code, name, account_type FROM accounts"
               " WHERE active=1 AND posting_allowed=1")
        params: tuple = ()
        if account_types:
            sql += f" AND account_type IN ({','.join('?' for _ in account_types)})"
            params = tuple(account_types)
        return self._query(sql + " ORDER BY code", params)

    def summary_accounts(self) -> list[dict]:
        return self._query("SELECT id, code, name, account_type FROM accounts"
                           " WHERE active=1 AND posting_allowed=0 ORDER BY code")
