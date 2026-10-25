"""JournalQueryService — asientos y sus líneas (§8.3)."""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)


class JournalQueryService(FinanceQueryServiceBase):
    @staticmethod
    def _filters(*, status, journal_type, date_from, date_to, search, source_module):
        conditions, params = ["1=1"], []
        for column, value in (("je.status", status), ("j.journal_type", journal_type),
                              ("je.source_module", source_module)):
            if value:
                conditions.append(f"{column} = ?")
                params.append(value)
        if date_from:
            conditions.append("je.posting_date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("je.posting_date <= ?")
            params.append(date_to)
        if search:
            conditions.append("(je.entry_number LIKE ? OR je.description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        return conditions, params

    def list_entries(self, *, status: str | None = None, journal_type: str | None = None,
                     date_from: str | None = None, date_to: str | None = None,
                     search: str | None = None, source_module: str | None = None,
                     limit: int = 200, offset: int = 0) -> list[dict]:
        """Página de asientos con su total en moneda base (F24: paginación del servidor)."""
        conditions, params = self._filters(
            status=status, journal_type=journal_type, date_from=date_from, date_to=date_to,
            search=search, source_module=source_module)
        params.extend([limit, offset])
        rows = self._query(
            "SELECT je.id, je.entry_number, je.entry_date, je.posting_date, je.description,"
            " je.status, j.journal_type, j.name AS journal_name, je.source_module,"
            " je.posting_purpose, je.branch_id, je.currency_code, je.base_currency_code,"
            " je.reversal_of_entry_id, je.reversed_by_entry_id, je.created_by,"
            " je.validated_by, je.posted_by"
            " FROM journal_entries je JOIN journals j ON j.id = je.journal_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY je.posting_date DESC, je.entry_number DESC LIMIT ? OFFSET ?",
            tuple(params))
        if rows:
            marks = ",".join("?" for _ in rows)
            totals: dict[str, list] = {}
            for line in self._query(
                    "SELECT journal_entry_id, base_debit_amount FROM journal_lines"
                    f" WHERE journal_entry_id IN ({marks})", tuple(r["id"] for r in rows)):
                totals.setdefault(line["journal_entry_id"], []).append(line["base_debit_amount"])
            for row in rows:
                row["total"] = money_text(decimal_sum(totals.get(row["id"], [])))
        return rows

    def count_entries(self, *, status: str | None = None, journal_type: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      search: str | None = None, source_module: str | None = None) -> int:
        conditions, params = self._filters(
            status=status, journal_type=journal_type, date_from=date_from, date_to=date_to,
            search=search, source_module=source_module)
        return int(self._scalar(
            "SELECT COUNT(*) FROM journal_entries je JOIN journals j ON j.id = je.journal_id"
            f" WHERE {' AND '.join(conditions)}", tuple(params)))

    def entry_lines(self, journal_entry_id: str) -> list[dict]:
        return self._query(
            "SELECT jl.line_index, jl.account_id, a.code AS account_code,"
            " a.name AS account_name, jl.description, jl.debit_amount, jl.credit_amount,"
            " jl.base_debit_amount, jl.base_credit_amount, jl.currency_code, jl.exchange_rate,"
            " jl.line_role, jl.branch_id, jl.cost_center_id, jl.profit_center_id,"
            " jl.project_id, jl.department_id, jl.customer_id, jl.supplier_id,"
            " jl.employee_id, jl.product_id, jl.source_reference"
            " FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id"
            " WHERE jl.journal_entry_id = ? ORDER BY jl.line_index", (journal_entry_id,))

    def entry_header(self, journal_entry_id: str) -> dict | None:
        return self._query_one(
            "SELECT je.*, j.journal_type, j.name AS journal_name FROM journal_entries je"
            " JOIN journals j ON j.id = je.journal_id WHERE je.id = ?", (journal_entry_id,))

    def unposted(self) -> list[dict]:
        return self.list_entries(status="DRAFT", limit=500) + \
            self.list_entries(status="VALIDATED", limit=500)

    def journals(self) -> list[dict]:
        return self._query("SELECT id, journal_type, name FROM journals WHERE active=1"
                           " ORDER BY name")
