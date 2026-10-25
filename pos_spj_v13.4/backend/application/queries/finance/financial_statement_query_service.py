"""FinancialStatementQueryService — estados financieros desde asientos CONTABILIZADOS (§31).

Nunca desde ventas, compras o caja: la única fuente es el mayor. Filtros por
periodo, sucursal, centro de costo, centro de utilidad y proyecto; comparativo
entre dos periodos y consolidado multisucursal con revisión de eliminaciones.
Siempre valida Activo = Pasivo + Capital.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    LedgerFilter,
    money_text,
)
from backend.application.queries.finance.general_ledger_query_service import (
    GeneralLedgerQueryService,
)
from backend.domain.finance.services.cash_flow_builder import CashFlowBuilder
from backend.domain.finance.services.financial_statement_builder import (
    FinancialStatementBuilder,
    TrialBalanceRow,
)

#: Roles cuyos saldos son movimientos INTERNOS que deben netear a cero al
#: consolidar (traspasos en tránsito entre sucursales, cuenta puente).
_INTERNAL_ROLES = ("inventory_in_transit_account_id", "clearing_account_id")


class FinancialStatementQueryService(FinanceQueryServiceBase):
    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._ledger = GeneralLedgerQueryService(connection)
        self._currency = self._ledger.base_currency()
        self._builder = FinancialStatementBuilder(self._currency)

    @staticmethod
    def _filter(**kwargs) -> LedgerFilter:
        return LedgerFilter(**{k: v for k, v in kwargs.items()
                               if k in LedgerFilter.__dataclass_fields__})

    def profile_accounts(self, key: str, roles: tuple[str, ...]) -> frozenset[str]:
        ids: set[str] = set()
        for row in self._query("SELECT accounts_json FROM posting_profiles"
                               " WHERE profile_key=? AND active=1", (key,)):
            accounts = json.loads(row["accounts_json"] or "{}")
            ids.update(accounts[r] for r in roles if accounts.get(r))
        return frozenset(ids)

    # ── estados ───────────────────────────────────────────────────────────
    def trial_balance(self, **filters) -> list[TrialBalanceRow]:
        return self._builder.trial_balance(self._ledger.account_balances(self._filter(**filters)))

    def balance_sheet(self, *, as_of: str | None = None, **filters) -> dict:
        rows = self._ledger.account_balances(self._filter(date_to=as_of, **filters))
        return self._builder.balance_sheet(rows)

    def income_statement(self, **filters) -> dict:
        rows = self._ledger.account_balances(self._filter(**filters))
        return self._builder.income_statement(
            rows, income_tax_account_ids=self.profile_accounts(
                "INCOME_TAX", ("income_tax_expense_account_id",)))

    def cash_flow_statement(self, *, date_from: str | None = None, date_to: str | None = None,
                            branch_id: str | None = None) -> dict:
        """Método directo sobre el efectivo real (F04): la variación neta
        reconcilia con efectivo final − inicial del rango."""
        cash_ids = self._ledger.cash_account_ids()
        entries = self._ledger.cash_flow_entries(cash_ids, date_from=date_from,
                                                 date_to=date_to, branch_id=branch_id)
        opening = (self._ledger.cash_balance(cash_ids, before=date_from, branch_id=branch_id)
                   if date_from else Decimal("0"))
        closing = self._ledger.cash_balance(cash_ids, until=date_to, branch_id=branch_id)
        return CashFlowBuilder(self._currency).build(entries, opening_cash=opening,
                                                     closing_cash=closing)

    def equity_changes(self, *, opening_to: str, closing_to: str,
                       branch_id: str | None = None) -> dict:
        opening = self._ledger.account_balances(self._filter(date_to=opening_to,
                                                             branch_id=branch_id))
        closing = self._ledger.account_balances(self._filter(date_to=closing_to,
                                                             branch_id=branch_id))
        return self._builder.equity_changes(opening, closing)

    # ── comparativo y consolidado ─────────────────────────────────────────
    def comparative_income_statement(self, *, current_from: str, current_to: str,
                                     previous_from: str, previous_to: str,
                                     **filters) -> dict:
        current = self.income_statement(date_from=current_from, date_to=current_to, **filters)
        previous = self.income_statement(date_from=previous_from, date_to=previous_to,
                                         **filters)
        lines = []
        for key in ("net_revenue", "cost_of_sales", "gross_profit", "operating_expenses",
                    "operating_income", "other_income", "other_expense",
                    "income_before_taxes", "income_taxes", "net_income"):
            now, before = Decimal(current[key]), Decimal(previous[key])
            change = now - before
            percent = (change * Decimal("100") / abs(before)).quantize(Decimal("0.1")) \
                if before != 0 else None
            lines.append({"key": key, "current": money_text(now), "previous": money_text(before),
                          "change": money_text(change),
                          "change_percent": format(percent, "f") if percent is not None else ""})
        return {"current": current, "previous": previous, "lines": lines}

    def consolidated_balance_sheet(self, *, as_of: str) -> dict:
        """Balance por sucursal, consolidado y revisión de eliminaciones: las
        cuentas internas (tránsito entre sucursales, cuenta puente) deben
        netear a cero en el consolidado; su residuo se muestra para revisión."""
        branches = [r["branch_id"] for r in self._query(
            "SELECT DISTINCT COALESCE(jl.branch_id, je.branch_id) AS branch_id"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            " WHERE je.status IN ('POSTED','REVERSED')")]
        per_branch = {}
        for branch in branches:
            if branch is None:
                continue
            rows = self._ledger.account_balances(self._filter(date_to=as_of, branch_id=branch))
            per_branch[branch] = {
                "assets": money_text(sum((r.natural_balance().amount for r in rows
                                          if r.account_type.value == "ASSET"), Decimal("0"))),
                "liabilities": money_text(sum((r.natural_balance().amount for r in rows
                                               if r.account_type.value == "LIABILITY"),
                                              Decimal("0"))),
                "net_income": self._builder.net_income(rows).to_string(),
            }
        consolidated_rows = self._ledger.account_balances(self._filter(date_to=as_of))
        consolidated = self._builder.balance_sheet(consolidated_rows)
        internal_ids = set()
        for key in ("INVENTORY", "TREASURY", "SALE", "CASH_SHIFT"):
            internal_ids |= self.profile_accounts(key, _INTERNAL_ROLES)
        eliminations = [
            {"code": r.account_code, "name": r.account_name,
             "residual": r.natural_balance().to_string()}
            for r in consolidated_rows if r.account_id in internal_ids
            and not r.natural_balance().is_zero()]
        return {"as_of": as_of, "per_branch": per_branch, "consolidated": consolidated,
                "eliminations_pending": eliminations}

    def account_auxiliary(self, account_id: str, *, date_from: str, date_to: str,
                          branch_id: str | None = None) -> dict:
        return self._ledger.account_auxiliary(account_id, date_from=date_from,
                                              date_to=date_to, branch_id=branch_id)
