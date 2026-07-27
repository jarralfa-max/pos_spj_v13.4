"""Fiscal period lifecycle: OPEN → SOFT_CLOSED → CLOSED → controlled reopen."""

from datetime import date

import pytest

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.enums import FiscalPeriodStatus
from backend.domain.finance.exceptions import PeriodClosedError, PeriodStateError
from backend.shared.ids import new_uuid


class TestFiscalPeriodLifecycle:
    def test_open_period_allows_posting(self):
        period = FiscalPeriod.open_for(2026, 7)
        period.assert_open_for_posting()  # must not raise
        assert period.contains(date(2026, 7, 31))
        assert not period.contains(date(2026, 8, 1))

    def test_soft_close_blocks_posting(self):
        period = FiscalPeriod.open_for(2026, 7)
        period.soft_close()
        assert period.status is FiscalPeriodStatus.SOFT_CLOSED
        with pytest.raises(PeriodClosedError):
            period.assert_open_for_posting()

    def test_close_blocks_posting(self):
        period = FiscalPeriod.open_for(2026, 7)
        period.close(closed_by=new_uuid())
        assert period.status is FiscalPeriodStatus.CLOSED
        with pytest.raises(PeriodClosedError):
            period.assert_open_for_posting()

    def test_reopen_requires_reason(self):
        period = FiscalPeriod.open_for(2026, 7)
        period.close(closed_by=new_uuid())
        with pytest.raises(PeriodStateError):
            period.reopen("")
        period.reopen("ajuste autorizado por auditoría")
        assert period.status is FiscalPeriodStatus.OPEN
        assert period.reopen_reason == "ajuste autorizado por auditoría"

    def test_cannot_reopen_open_period(self):
        period = FiscalPeriod.open_for(2026, 7)
        with pytest.raises(PeriodStateError):
            period.reopen("sin sentido")

    def test_invalid_month_rejected(self):
        from backend.domain.finance.exceptions import FinanceDomainError
        with pytest.raises(FinanceDomainError):
            FiscalPeriod.open_for(2026, 13)
