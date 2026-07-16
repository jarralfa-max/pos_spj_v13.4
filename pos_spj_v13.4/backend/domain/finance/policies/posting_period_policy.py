"""Posting period policy — no posting into soft-closed or closed periods."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.exceptions import PeriodNotFoundError


class PostingPeriodPolicy:
    def enforce(self, period: FiscalPeriod | None, entry_date: date) -> None:
        if period is None:
            raise PeriodNotFoundError(f"No fiscal period covers date {entry_date.isoformat()}")
        if not period.contains(entry_date):
            raise PeriodNotFoundError(
                f"Date {entry_date.isoformat()} is outside fiscal period {period.period.code()}"
            )
        period.assert_open_for_posting()
