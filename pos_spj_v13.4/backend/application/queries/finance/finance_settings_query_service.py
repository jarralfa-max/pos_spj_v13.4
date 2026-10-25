"""FinanceSettingsQueryService — configuración visible: parámetros, perfiles
contables (con el código y nombre de cada cuenta), impuestos, monedas y
dimensiones."""

from __future__ import annotations

import json
from datetime import date

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
)
from backend.domain.finance.entities.finance_settings import FinanceSettings


class FinanceSettingsQueryService(FinanceQueryServiceBase):
    def settings(self) -> FinanceSettings:
        raw = {r["setting_key"]: r["setting_value"] for r in self._query(
            "SELECT setting_key, setting_value FROM finance_settings")}
        return FinanceSettings.from_storage(raw)

    def posting_profiles(self, *, on_date: str | None = None) -> list[dict]:
        today = on_date or date.today().isoformat()
        accounts = {r["id"]: r for r in self._query("SELECT id, code, name FROM accounts")}
        rows = self._query(
            "SELECT id, profile_key, description, accounts_json, instrument_type,"
            " effective_from, effective_to, branch_id, funding_party, active"
            " FROM posting_profiles ORDER BY profile_key, effective_from")
        for row in rows:
            roles = json.loads(row.pop("accounts_json") or "{}")
            row["roles"] = [
                {"role": role, "account_id": account_id,
                 "account_code": accounts.get(account_id, {}).get("code", ""),
                 "account_name": accounts.get(account_id, {}).get("name", "")}
                for role, account_id in sorted(roles.items())]
            row["current"] = bool(row["active"]) and row["effective_from"] <= today and (
                not row["effective_to"] or row["effective_to"] >= today)
        return rows

    def taxes(self) -> list[dict]:
        today = date.today().isoformat()
        rows = self._query("SELECT id, code, name, kind, direction, active FROM tax_codes"
                           " ORDER BY code")
        for row in rows:
            rate = self._query_one(
                "SELECT rate_percent, effective_from FROM tax_rates WHERE tax_code_id=?"
                " AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)"
                " ORDER BY effective_from DESC LIMIT 1", (row["id"], today, today))
            row["rate_percent"] = rate["rate_percent"] if rate else ""
            row["rules"] = self._query("SELECT scope, scope_id, effective_from, effective_to"
                                       " FROM tax_rules WHERE tax_code_id=? AND active=1",
                                       (row["id"],))
        return rows

    def currencies(self) -> list[dict]:
        return self._query("SELECT id, code, name, decimal_places, active FROM currencies"
                           " ORDER BY code")

    def exchange_rates(self, limit: int = 100) -> list[dict]:
        return self._query("SELECT id, from_currency, to_currency, rate, effective_date, source"
                           " FROM exchange_rates ORDER BY effective_date DESC LIMIT ?", (limit,))

    def dimensions(self) -> dict[str, list[dict]]:
        return {
            "cost_centers": self._query("SELECT id, code, name, branch_id FROM cost_centers"
                                        " WHERE active=1 ORDER BY code"),
            "profit_centers": self._query("SELECT id, code, name, branch_id FROM profit_centers"
                                          " WHERE active=1 ORDER BY code"),
            "projects": self._query("SELECT id, code, name, branch_id, is_capex FROM projects"
                                    " WHERE active=1 ORDER BY code"),
            "departments": self._query("SELECT id, code, name FROM departments WHERE active=1"
                                       " ORDER BY code"),
        }

    def treasury_accounts(self) -> list[dict]:
        return self._query("SELECT ta.id, ta.name, ta.account_type, ta.currency_code,"
                           " ta.masked_account_number, ta.bank_name, ta.restricted,"
                           " ta.allows_overdraft, ta.active, a.code AS ledger_code"
                           " FROM treasury_accounts ta JOIN accounts a"
                           " ON a.id = ta.ledger_account_id ORDER BY ta.name")
