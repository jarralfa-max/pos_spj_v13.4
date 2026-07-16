"""FinancialStatementQueryService — canonical statements for UI, exports and BI."""

from __future__ import annotations

from backend.application.queries.finance.general_ledger_query_service import (
    GeneralLedgerQueryService,
)
from backend.domain.finance.services.financial_statement_builder import (
    FinancialStatementBuilder,
    TrialBalanceRow,
)


class FinancialStatementQueryService:
    def __init__(self, connection, currency_code: str = "MXN") -> None:
        self._ledger = GeneralLedgerQueryService(connection)
        self._builder = FinancialStatementBuilder(currency_code)

    def trial_balance(self, *, date_from: str | None = None, date_to: str | None = None,
                      branch_id: str | None = None) -> list[TrialBalanceRow]:
        rows = self._ledger.account_balances(date_from=date_from, date_to=date_to,
                                             branch_id=branch_id)
        return self._builder.trial_balance(rows)

    def balance_sheet(self, *, as_of: str | None = None, branch_id: str | None = None) -> dict:
        rows = self._ledger.account_balances(date_to=as_of, branch_id=branch_id)
        return self._builder.balance_sheet(rows)

    def income_statement(self, *, date_from: str | None = None, date_to: str | None = None,
                         branch_id: str | None = None) -> dict:
        rows = self._ledger.account_balances(date_from=date_from, date_to=date_to,
                                             branch_id=branch_id)
        return self._builder.income_statement(rows)

    def cash_flow_statement(self, *, date_from: str | None = None,
                            date_to: str | None = None,
                            branch_id: str | None = None) -> dict:
        rows = self._ledger.account_balances(date_from=date_from, date_to=date_to,
                                             branch_id=branch_id)
        return self._builder.cash_flow_statement(rows)

    def equity_changes(self, *, opening_to: str, closing_to: str,
                       branch_id: str | None = None) -> dict:
        opening = self._ledger.account_balances(date_to=opening_to, branch_id=branch_id)
        closing = self._ledger.account_balances(date_to=closing_to, branch_id=branch_id)
        return self._builder.equity_changes(opening, closing)
