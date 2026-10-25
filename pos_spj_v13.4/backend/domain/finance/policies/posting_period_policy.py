"""Posting period policy (§9).

OPEN        → operaciones normales.
SOFT_CLOSED → sólo ajustes con permiso especial (``allow_soft_closed``, que
              concede quien llama tras exigir ``FINANZAS.ajuste.periodo_cerrado``).
CLOSED      → prohíbe toda contabilización.
"""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.enums import FiscalPeriodStatus
from backend.domain.finance.exceptions import (
    ClosedFiscalPeriodError,
    InvalidAccountingDateError,
    PeriodNotFoundError,
)


class PostingPeriodPolicy:
    def enforce(self, period: FiscalPeriod | None, entry_date: date, *,
                allow_soft_closed: bool = False) -> None:
        if not isinstance(entry_date, date):
            raise InvalidAccountingDateError(f"Fecha contable inválida: {entry_date!r}")
        if period is None:
            raise PeriodNotFoundError(f"Ningún periodo contable cubre el {entry_date.isoformat()}")
        if not period.contains(entry_date):
            raise InvalidAccountingDateError(
                f"La fecha {entry_date.isoformat()} está fuera del periodo {period.period.code()}")
        if period.status is FiscalPeriodStatus.SOFT_CLOSED and allow_soft_closed:
            return
        period.assert_open_for_posting()
