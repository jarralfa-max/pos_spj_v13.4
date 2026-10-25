"""TrialBalanceQueryService — balanza de comprobación (§31) en moneda base.

Siempre cuadra (débitos = créditos) o falla de forma explícita: una balanza
descuadrada es un error de integridad del mayor, no un dato que mostrar.
"""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    decimal_sum,
    money_text,
)
from backend.application.queries.finance.financial_statement_query_service import (
    FinancialStatementQueryService,
)


class TrialBalanceQueryService:
    def __init__(self, connection) -> None:
        self._statements = FinancialStatementQueryService(connection)

    def trial_balance(self, **filters) -> dict:
        rows = self._statements.trial_balance(**filters)
        return {
            "rows": rows,
            "total_debits": money_text(decimal_sum(r.debit_total for r in rows)),
            "total_credits": money_text(decimal_sum(r.credit_total for r in rows)),
        }
