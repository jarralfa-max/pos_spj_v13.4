"""FixedAssetQueryService — activos, categorías, corridas y préstamos (§17)."""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)


class FixedAssetQueryService(FinanceQueryServiceBase):
    def list_assets(self, *, status: str | None = None) -> list[dict]:
        sql = ("SELECT fa.id, fa.asset_code, fa.name, fa.acquisition_cost, fa.residual_value,"
               " fa.accumulated_depreciation, fa.useful_life_months, fa.status,"
               " fa.status_reason, fa.capitalization_date, fa.acquisition_date,"
               " fa.last_depreciated_period, fa.branch_id, fa.project_id,"
               " c.name AS category_name, p.name AS project_name FROM fixed_assets fa"
               " LEFT JOIN fixed_asset_categories c ON c.id = fa.asset_category_id"
               " LEFT JOIN projects p ON p.id = fa.project_id")
        params: tuple = ()
        if status:
            sql += " WHERE fa.status = ?"
            params = (status,)
        rows = self._query(sql + " ORDER BY fa.name", params)
        for row in rows:
            row["net_book_value"] = money_text(decimal_sum([row["acquisition_cost"]])
                                               - decimal_sum([row["accumulated_depreciation"]]))
        return rows

    def categories(self) -> list[dict]:
        return self._query("SELECT id, code, name, default_useful_life_months"
                           " FROM fixed_asset_categories WHERE active=1 ORDER BY name")

    def depreciation_runs(self) -> list[dict]:
        return self._query("SELECT id, period_code, asset_count, total_amount, run_by, run_at"
                           " FROM depreciation_runs ORDER BY run_at DESC LIMIT 100")

    def capex_by_project(self) -> list[dict]:
        grouped: dict[str, dict] = {}
        for row in self._query(
                "SELECT p.code, p.name, fa.acquisition_cost FROM fixed_assets fa"
                " JOIN projects p ON p.id = fa.project_id WHERE fa.status <> 'DRAFT'"):
            bucket = grouped.setdefault(row["code"], {"code": row["code"], "name": row["name"],
                                                      "values": []})
            bucket["values"].append(row["acquisition_cost"])
        return [{"code": b["code"], "name": b["name"],
                 "capex": money_text(decimal_sum(b["values"]))} for b in grouped.values()]

    def loans(self) -> list[dict]:
        return self._query("SELECT id, lender_name, principal_amount, outstanding_principal,"
                           " currency_code, start_date, maturity_date, status FROM loans"
                           " ORDER BY status, start_date")

    def capital_transactions(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT ct.id, ct.kind, ct.amount, ct.interest_amount, ct.transaction_date,"
            " ct.counterparty, ta.name AS treasury_account_name, je.entry_number"
            " FROM capital_transactions ct JOIN treasury_accounts ta"
            " ON ta.id = ct.treasury_account_id LEFT JOIN journal_entries je"
            " ON je.id = ct.journal_entry_id ORDER BY ct.transaction_date DESC LIMIT ?",
            (limit,))
