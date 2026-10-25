"""TreasuryQueryService — posición de tesorería (§13).

Por cuenta: saldo CONTABLE (mayor), saldo CONCILIADO (saldo final del último
estado de cuenta conciliado) y saldo DISPONIBLE (contable menos pagos ya
programados/autorizados; cero si la cuenta es de fondos restringidos).

F05: sólo asientos contabilizados de la moneda de la cuenta; si dos cuentas
comparten espejo se marcan ``shared_mirror`` y el total las cuenta una vez.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.queries.finance.base_finance_query_service import (
    POSTED,
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)


class TreasuryQueryService(FinanceQueryServiceBase):
    def _mirror_balance(self, ledger_account_id: str, currency_code: str) -> Decimal:
        rows = self._query(
            "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            f" WHERE jl.account_id = ? AND je.status IN {POSTED} AND jl.currency_code = ?",
            (ledger_account_id, currency_code))
        return (decimal_sum(r["debit_amount"] for r in rows)
                - decimal_sum(r["credit_amount"] for r in rows))

    def treasury_position(self) -> list[dict]:
        accounts = self._query(
            "SELECT ta.id, ta.name, ta.account_type, ta.currency_code, ta.branch_id,"
            " ta.ledger_account_id, ta.bank_name, ta.masked_account_number, ta.restricted,"
            " ta.allows_overdraft, ta.requires_reconciliation"
            " FROM treasury_accounts ta WHERE ta.active = 1 ORDER BY ta.name")
        sharing: dict[str, int] = {}
        for account in accounts:
            sharing[account["ledger_account_id"]] = sharing.get(account["ledger_account_id"],
                                                                0) + 1
        for account in accounts:
            balance = self._mirror_balance(account["ledger_account_id"],
                                           account["currency_code"])
            committed = decimal_sum(r["amount"] for r in self._query(
                "SELECT amount FROM supplier_payments WHERE treasury_account_id=?"
                " AND status IN ('SCHEDULED','AUTHORIZED')", (account["id"],)))
            reconciled = self._query_one(
                "SELECT bs.closing_balance, bs.statement_date FROM reconciliations r"
                " JOIN bank_statements bs ON bs.id = r.bank_statement_id"
                " WHERE r.treasury_account_id=? AND r.status='COMPLETED'"
                " ORDER BY bs.statement_date DESC LIMIT 1", (account["id"],))
            account["balance"] = money_text(balance)
            account["committed"] = money_text(committed)
            account["available"] = money_text(Decimal("0") if account["restricted"]
                                              else balance - committed)
            account["reconciled_balance"] = reconciled["closing_balance"] if reconciled else ""
            account["reconciled_as_of"] = reconciled["statement_date"] if reconciled else ""
            account["shared_mirror"] = sharing[account["ledger_account_id"]] > 1
            account["restricted"] = bool(account["restricted"])
        return accounts

    def treasury_total(self) -> dict[str, str]:
        """Total por moneda contando cada espejo UNA vez (cuadra con el mayor)."""
        seen: set[tuple[str, str]] = set()
        totals: dict[str, Decimal] = {}
        for account in self.treasury_position():
            key = (account["ledger_account_id"], account["currency_code"])
            if key in seen:
                continue
            seen.add(key)
            totals[account["currency_code"]] = totals.get(account["currency_code"],
                                                          Decimal("0")) + Decimal(account["balance"])
        return {currency: money_text(total) for currency, total in totals.items()}

    def available_total(self) -> dict[str, str]:
        totals: dict[str, Decimal] = {}
        seen: set[str] = set()
        for account in self.treasury_position():
            if account["ledger_account_id"] in seen:
                continue
            seen.add(account["ledger_account_id"])
            totals[account["currency_code"]] = totals.get(account["currency_code"],
                                                          Decimal("0")) + Decimal(account["available"])
        return {currency: money_text(total) for currency, total in totals.items()}

    def statements(self, treasury_account_id: str) -> list[dict]:
        return self._query(
            "SELECT id, statement_date, opening_balance, closing_balance, source_format,"
            " file_name, imported_by, imported_at FROM bank_statements"
            " WHERE treasury_account_id = ? ORDER BY statement_date DESC",
            (treasury_account_id,))

    def movements(self, *, treasury_account_id: str | None = None, limit: int = 200) -> list[dict]:
        sql = ("SELECT tm.id, tm.kind, tm.amount, tm.currency_code, tm.movement_date,"
               " tm.reference, tm.description, ta.name AS treasury_account_name,"
               " a.code AS counterpart_code, a.name AS counterpart_name, je.entry_number"
               " FROM treasury_movements tm JOIN treasury_accounts ta"
               " ON ta.id = tm.treasury_account_id JOIN accounts a"
               " ON a.id = tm.counterpart_account_id"
               " LEFT JOIN journal_entries je ON je.id = tm.journal_entry_id")
        params: tuple = ()
        if treasury_account_id:
            sql += " WHERE tm.treasury_account_id = ?"
            params = (treasury_account_id,)
        return self._query(sql + " ORDER BY tm.movement_date DESC LIMIT ?", params + (limit,))
