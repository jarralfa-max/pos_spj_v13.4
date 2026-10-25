"""FiscalPeriodQueryService — periodos contables y su historia de cierre (§9)."""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
)


class FiscalPeriodQueryService(FinanceQueryServiceBase):
    def fiscal_periods(self) -> list[dict]:
        return self._query(
            "SELECT id, year, month, status, soft_closed_at, soft_closed_by, closed_at,"
            " closed_by, reopened_at, reopened_by, reopen_reason"
            " FROM fiscal_periods ORDER BY year DESC, month DESC")

    def open_close_exceptions(self, period_code: str | None = None) -> list[dict]:
        if period_code is None:
            return self._query("SELECT * FROM finance_close_exceptions WHERE status='OPEN'"
                               " ORDER BY period_code, check_type")
        return self._query("SELECT * FROM finance_close_exceptions WHERE status='OPEN'"
                           " AND period_code<=? ORDER BY period_code, check_type",
                           (period_code,))
