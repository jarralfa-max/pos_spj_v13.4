"""GeneralLedgerQueryService — lecturas del mayor CONTABILIZADO (§31).

- Importes en MONEDA BASE (las líneas en moneda extranjera traen su importe
  base y la diferencia de redondeo va en su propia línea): una balanza siempre
  cuadra en una sola moneda.
- Sucursal por LÍNEA (con la del asiento si la línea no la trae): un traspaso
  entre sucursales separa origen y destino.
- Sumas en Decimal (F20). Flujo de efectivo por método directo (F04).
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.queries.finance.base_finance_query_service import (
    LINE_BRANCH,
    POSTED,
    FinanceQueryServiceBase,
    LedgerFilter,
    decimal_sum,
    money_text,
)
from backend.domain.finance.enums import AccountType, CashFlowCategory, NormalBalance
from backend.domain.finance.services.cash_flow_builder import CashFlowEntry, CashFlowLine
from backend.domain.finance.services.financial_statement_builder import AccountBalanceRow
from backend.domain.finance.value_objects.money import Money

#: Tipos de cuenta de tesorería que son efectivo o equivalente. Un procesador
#: de pagos o una cuenta puente son por cobrar hasta que liquidan; un monedero
#: promocional no es dinero.
_CASH_TREASURY_TYPES = ("BANK", "GENERAL_CASH", "PETTY_CASH", "CASH_REGISTER")
_CASH_PROFILE_ROLES = ("cash_account_id", "bank_account_id")


class GeneralLedgerQueryService(FinanceQueryServiceBase):
    def base_currency(self) -> str:
        row = self._query_one("SELECT setting_value FROM finance_settings"
                              " WHERE setting_key='base_currency_code'")
        return (row["setting_value"] if row and row["setting_value"] else "MXN").upper()

    def account_balances(self, filters: LedgerFilter | None = None) -> list[AccountBalanceRow]:
        """Débitos/créditos por cuenta (moneda base) de asientos contabilizados."""
        filters = filters or LedgerFilter()
        conditions, params = filters.sql()
        rows = self._query(
            "SELECT a.id, a.code, a.name, a.account_type, a.normal_balance,"
            " a.cash_flow_category, jl.base_debit_amount, jl.base_credit_amount"
            " FROM accounts a JOIN journal_lines jl ON jl.account_id = a.id"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}", tuple(params))
        currency = self.base_currency()
        grouped: dict[str, dict] = {}
        for row in rows:
            bucket = grouped.setdefault(row["id"], {"row": row, "debits": [], "credits": []})
            bucket["debits"].append(row["base_debit_amount"])
            bucket["credits"].append(row["base_credit_amount"])
        result = []
        for bucket in sorted(grouped.values(), key=lambda b: b["row"]["code"]):
            row = bucket["row"]
            result.append(AccountBalanceRow(
                account_id=row["id"], account_code=row["code"], account_name=row["name"],
                account_type=AccountType(row["account_type"]),
                normal_balance=NormalBalance(row["normal_balance"]),
                total_debits=Money(decimal_sum(bucket["debits"]), currency),
                total_credits=Money(decimal_sum(bucket["credits"]), currency),
                cash_flow_category=CashFlowCategory(row["cash_flow_category"]),
            ))
        return result

    def ledger_lines(self, account_id: str, *, date_from: str | None = None,
                     date_to: str | None = None, branch_id: str | None = None,
                     limit: int = 500, offset: int = 0) -> list[dict]:
        filters = LedgerFilter(date_from=date_from, date_to=date_to, branch_id=branch_id)
        conditions, params = filters.sql()
        conditions.insert(0, "jl.account_id = ?")
        params.insert(0, account_id)
        params.extend([limit, offset])
        return self._query(
            "SELECT je.id AS journal_entry_id, je.posting_date AS entry_date, je.entry_number,"
            " je.description AS entry_description, jl.id AS journal_line_id, jl.description,"
            " jl.base_debit_amount AS debit_amount, jl.base_credit_amount AS credit_amount,"
            " jl.currency_code, jl.debit_amount AS foreign_debit,"
            " jl.credit_amount AS foreign_credit, jl.exchange_rate,"
            f" je.source_module, je.posting_purpose, {LINE_BRANCH} AS branch_id,"
            " je.reversal_of_entry_id, je.reversed_by_entry_id"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY je.posting_date, je.entry_number, jl.line_index LIMIT ? OFFSET ?",
            tuple(params))

    def count_ledger_lines(self, account_id: str) -> int:
        return int(self._scalar(
            "SELECT COUNT(*) FROM journal_lines jl JOIN journal_entries je"
            f" ON je.id = jl.journal_entry_id WHERE jl.account_id = ? AND je.status IN {POSTED}",
            (account_id,)))

    def account_auxiliary(self, account_id: str, *, date_from: str, date_to: str,
                          branch_id: str | None = None) -> dict:
        """Auxiliar por cuenta (§31): saldo inicial, movimientos con saldo
        acumulado y saldo final, según la naturaleza de la cuenta."""
        account = self._query_one("SELECT code, name, normal_balance FROM accounts WHERE id=?",
                                  (account_id,))
        if account is None:
            return {"account": None, "lines": []}
        debit_nature = account["normal_balance"] == "DEBIT"
        opening_filters = LedgerFilter(date_to=None, branch_id=branch_id)
        conditions, params = opening_filters.sql()
        conditions += ["jl.account_id = ?", "je.posting_date < ?"]
        params += [account_id, date_from]
        prior = self._query(
            "SELECT jl.base_debit_amount, jl.base_credit_amount FROM journal_lines jl"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}", tuple(params))
        delta = (decimal_sum(r["base_debit_amount"] for r in prior)
                 - decimal_sum(r["base_credit_amount"] for r in prior))
        balance = delta if debit_nature else -delta
        opening = balance
        lines = []
        for row in self.ledger_lines(account_id, date_from=date_from, date_to=date_to,
                                     branch_id=branch_id, limit=100000):
            movement = decimal_sum([row["debit_amount"]]) - decimal_sum([row["credit_amount"]])
            balance += movement if debit_nature else -movement
            lines.append({**row, "running_balance": money_text(balance)})
        return {"account": {"id": account_id, **account}, "opening_balance": money_text(opening),
                "closing_balance": money_text(balance), "lines": lines}

    # ── efectivo (F04) ────────────────────────────────────────────────────
    def cash_account_ids(self) -> set[str]:
        """Efectivo y equivalentes: espejos de cuentas de tesorería de dinero
        más las cuentas que los perfiles contables usan como efectivo o banco."""
        placeholders = ",".join("?" for _ in _CASH_TREASURY_TYPES)
        ids = {row["ledger_account_id"] for row in self._query(
            f"SELECT ledger_account_id FROM treasury_accounts WHERE account_type IN ({placeholders})",
            _CASH_TREASURY_TYPES)}
        for row in self._query("SELECT accounts_json FROM posting_profiles WHERE active = 1"):
            accounts = json.loads(row["accounts_json"] or "{}")
            for role in _CASH_PROFILE_ROLES:
                if accounts.get(role):
                    ids.add(accounts[role])
        return ids

    def cash_balance(self, cash_ids: set[str], *, before: str | None = None,
                     until: str | None = None, branch_id: str | None = None) -> Decimal:
        if not cash_ids:
            return Decimal("0")
        filters = LedgerFilter(date_to=until, branch_id=branch_id)
        conditions, params = filters.sql()
        placeholders = ",".join("?" for _ in cash_ids)
        conditions.append(f"jl.account_id IN ({placeholders})")
        params.extend(cash_ids)
        if before:
            conditions.append("je.posting_date < ?")
            params.append(before)
        rows = self._query(
            "SELECT jl.base_debit_amount, jl.base_credit_amount FROM journal_lines jl"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}", tuple(params))
        return (decimal_sum(r["base_debit_amount"] for r in rows)
                - decimal_sum(r["base_credit_amount"] for r in rows))

    def cash_flow_entries(self, cash_ids: set[str], *, date_from: str | None = None,
                          date_to: str | None = None,
                          branch_id: str | None = None) -> list[CashFlowEntry]:
        """Asientos del rango que tocan al menos una cuenta de efectivo, con todas sus líneas."""
        if not cash_ids:
            return []
        filters = LedgerFilter(date_from=date_from, date_to=date_to, branch_id=branch_id)
        conditions, params = filters.sql()
        placeholders = ",".join("?" for _ in cash_ids)
        conditions.append(f"je.id IN (SELECT journal_entry_id FROM journal_lines"
                          f" WHERE account_id IN ({placeholders}))")
        params.extend(cash_ids)
        rows = self._query(
            "SELECT je.id AS entry_id, jl.account_id, a.cash_flow_category,"
            " jl.base_debit_amount, jl.base_credit_amount"
            " FROM journal_entries je JOIN journal_lines jl ON jl.journal_entry_id = je.id"
            " JOIN accounts a ON a.id = jl.account_id"
            f" WHERE {' AND '.join(conditions)} ORDER BY je.posting_date, je.entry_number,"
            " jl.line_index", tuple(params))
        entries: dict[str, CashFlowEntry] = {}
        for row in rows:
            entry = entries.setdefault(row["entry_id"], CashFlowEntry(row["entry_id"]))
            entry.lines.append(CashFlowLine(
                account_id=row["account_id"], is_cash=row["account_id"] in cash_ids,
                category=CashFlowCategory(row["cash_flow_category"]),
                debit=decimal_sum([row["base_debit_amount"]]),
                credit=decimal_sum([row["base_credit_amount"]])))
        return list(entries.values())
