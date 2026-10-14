"""GeneralLedgerQueryService — POSTED-only ledger reads for UI and BI.

Auditoría d9f2bca:
- F06: los saldos se calculan POR MONEDA. Antes 100 MXN + 100 USD devolvían
  "200 MXN": la moneda del resultado etiquetaba la suma, no filtraba sus
  fuentes. Ahora sólo entran asientos en ``currency_code``.
- F20: la suma es Decimal en Python, no ``SUM(CAST(... AS NUMERIC))`` de SQLite
  (que pasa por real binario y perdía centavos en importes grandes).
- F04: ``cash_flow_entries`` alimenta el flujo de efectivo por método directo.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
)
from backend.domain.finance.enums import AccountType, CashFlowCategory, NormalBalance
from backend.domain.finance.services.cash_flow_builder import CashFlowEntry, CashFlowLine
from backend.domain.finance.services.financial_statement_builder import AccountBalanceRow
from backend.domain.finance.value_objects.money import Money

_POSTED = "('POSTED','REVERSED')"  # reversed originals stay in the ledger; reversal entries offset them

#: Tipos de cuenta de tesorería que son efectivo o equivalente. Un procesador
#: de pagos o una cuenta puente son por cobrar hasta que liquidan; un monedero
#: promocional no es dinero.
_CASH_TREASURY_TYPES = ("BANK", "GENERAL_CASH", "PETTY_CASH", "CASH_REGISTER")
_CASH_PROFILE_ROLES = ("cash_account_id", "bank_account_id")


class GeneralLedgerQueryService(FinanceQueryServiceBase):
    def account_balances(self, *, date_from: str | None = None, date_to: str | None = None,
                         branch_id: str | None = None,
                         currency_code: str = "MXN") -> list[AccountBalanceRow]:
        """Aggregated debit/credit per account from POSTED entries of ONE currency."""
        conditions = [f"je.status IN {_POSTED}", "je.currency_code = ?"]
        params: list = [currency_code]
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
            " a.cash_flow_category, jl.debit_amount, jl.credit_amount"
            " FROM accounts a"
            " JOIN journal_lines jl ON jl.account_id = a.id"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}",
            tuple(params),
        )
        grouped: dict[str, dict] = {}
        for row in rows:
            bucket = grouped.setdefault(row["id"], {"row": row, "debits": [], "credits": []})
            bucket["debits"].append(row["debit_amount"])
            bucket["credits"].append(row["credit_amount"])
        result = []
        for bucket in sorted(grouped.values(), key=lambda b: b["row"]["code"]):
            row = bucket["row"]
            result.append(AccountBalanceRow(
                account_id=row["id"], account_code=row["code"], account_name=row["name"],
                account_type=AccountType(row["account_type"]),
                normal_balance=NormalBalance(row["normal_balance"]),
                total_debits=Money(decimal_sum(bucket["debits"]), currency_code),
                total_credits=Money(decimal_sum(bucket["credits"]), currency_code),
                cash_flow_category=CashFlowCategory(row["cash_flow_category"]),
            ))
        return result

    def ledger_lines(self, account_id: str, *, date_from: str | None = None,
                     date_to: str | None = None, limit: int = 500,
                     offset: int = 0) -> list[dict]:
        conditions = ["jl.account_id = ?", f"je.status IN {_POSTED}"]
        params: list = [account_id]
        if date_from:
            conditions.append("je.entry_date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("je.entry_date <= ?")
            params.append(date_to)
        params.extend([limit, offset])
        return self._query(
            "SELECT je.id AS journal_entry_id, je.entry_date, je.entry_number,"
            " je.description AS entry_description,"
            " jl.id AS journal_line_id, jl.description, jl.debit_amount, jl.credit_amount,"
            " je.source_module, je.posting_purpose, je.branch_id, je.currency_code,"
            " je.reversal_of_entry_id, je.reversed_by_entry_id"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY je.entry_date, je.entry_number LIMIT ? OFFSET ?",
            tuple(params),
        )

    def count_ledger_lines(self, account_id: str) -> int:
        return int(self._scalar(
            "SELECT COUNT(*) FROM journal_lines jl JOIN journal_entries je"
            f" ON je.id = jl.journal_entry_id WHERE jl.account_id = ? AND je.status IN {_POSTED}",
            (account_id,)))

    def unmatched_treasury_lines(self, ledger_account_id: str, *, limit: int = 500) -> list[dict]:
        """POSTED lines on a treasury mirror account not yet reconciled."""
        return self._query(
            "SELECT jl.id AS journal_line_id, je.entry_date, je.entry_number,"
            " jl.debit_amount, jl.credit_amount, jl.description"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            " WHERE jl.account_id = ? AND je.status = 'POSTED'"
            " AND jl.id NOT IN (SELECT journal_line_id FROM reconciliation_matches"
            "                   WHERE active = 1)"
            " ORDER BY je.entry_date LIMIT ?",
            (ledger_account_id, limit),
        )

    # ── efectivo (F04) ────────────────────────────────────────────────────
    def cash_account_ids(self) -> set[str]:
        """Efectivo y equivalentes: espejos de cuentas de tesorería de dinero
        (banco, caja general, fondo fijo, cajas POS) más las cuentas que los
        perfiles contables usan como efectivo o banco."""
        placeholders = ",".join("?" for _ in _CASH_TREASURY_TYPES)
        ids = {row["ledger_account_id"] for row in self._query(
            f"SELECT ledger_account_id FROM treasury_accounts WHERE account_type IN ({placeholders})",
            _CASH_TREASURY_TYPES)}
        import json
        for row in self._query("SELECT accounts_json FROM posting_profiles WHERE active = 1"):
            try:
                accounts = json.loads(row["accounts_json"] or "{}")
            except ValueError:
                continue
            for role in _CASH_PROFILE_ROLES:
                if accounts.get(role):
                    ids.add(accounts[role])
        return ids

    def cash_balance(self, cash_ids: set[str], *, before: str | None = None,
                     until: str | None = None, branch_id: str | None = None,
                     currency_code: str = "MXN") -> Decimal:
        if not cash_ids:
            return Decimal("0")
        placeholders = ",".join("?" for _ in cash_ids)
        conditions = [f"je.status IN {_POSTED}", "je.currency_code = ?",
                      f"jl.account_id IN ({placeholders})"]
        params: list = [currency_code, *cash_ids]
        if before:
            conditions.append("je.entry_date < ?")
            params.append(before)
        if until:
            conditions.append("je.entry_date <= ?")
            params.append(until)
        if branch_id:
            conditions.append("je.branch_id = ?")
            params.append(branch_id)
        rows = self._query(
            "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}", tuple(params))
        return (decimal_sum(r["debit_amount"] for r in rows)
                - decimal_sum(r["credit_amount"] for r in rows))

    def cash_flow_entries(self, cash_ids: set[str], *, date_from: str | None = None,
                          date_to: str | None = None, branch_id: str | None = None,
                          currency_code: str = "MXN") -> list[CashFlowEntry]:
        """Asientos del rango que tocan al menos una cuenta de efectivo, con
        todas sus líneas."""
        if not cash_ids:
            return []
        placeholders = ",".join("?" for _ in cash_ids)
        conditions = [f"je.status IN {_POSTED}", "je.currency_code = ?",
                      f"je.id IN (SELECT journal_entry_id FROM journal_lines"
                      f" WHERE account_id IN ({placeholders}))"]
        params: list = [currency_code, *cash_ids]
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
            "SELECT je.id AS entry_id, jl.account_id, a.cash_flow_category,"
            " jl.debit_amount, jl.credit_amount"
            " FROM journal_entries je JOIN journal_lines jl ON jl.journal_entry_id = je.id"
            " JOIN accounts a ON a.id = jl.account_id"
            f" WHERE {' AND '.join(conditions)} ORDER BY je.entry_date, je.entry_number,"
            " jl.line_index", tuple(params))
        entries: dict[str, CashFlowEntry] = {}
        for row in rows:
            entry = entries.setdefault(row["entry_id"], CashFlowEntry(row["entry_id"]))
            entry.lines.append(CashFlowLine(
                account_id=row["account_id"], is_cash=row["account_id"] in cash_ids,
                category=CashFlowCategory(row["cash_flow_category"]),
                debit=decimal_sum([row["debit_amount"]]),
                credit=decimal_sum([row["credit_amount"]])))
        return list(entries.values())
