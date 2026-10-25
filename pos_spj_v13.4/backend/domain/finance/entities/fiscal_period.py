"""FiscalPeriod entity — monthly accounting period with controlled lifecycle (§9).

Reabrir exige motivo y queda quién y cuándo; cerrar queda con quién y cuándo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.enums import FiscalPeriodStatus
from backend.domain.finance.exceptions import ClosedFiscalPeriodError, PeriodStateError
from backend.domain.finance.value_objects.accounting_period import AccountingPeriod
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class FiscalPeriod:
    id: str
    year: int
    month: int
    status: FiscalPeriodStatus = FiscalPeriodStatus.OPEN
    opened_at: str = field(default_factory=_utcnow)
    soft_closed_at: str | None = None
    closed_at: str | None = None
    reopened_at: str | None = None
    closed_by: str | None = None
    reopen_reason: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    soft_closed_by: str | None = None
    reopened_by: str | None = None

    @classmethod
    def open_for(cls, year: int, month: int) -> "FiscalPeriod":
        AccountingPeriod(year, month)  # validates range
        return cls(id=new_uuid(), year=year, month=month)

    @property
    def period(self) -> AccountingPeriod:
        return AccountingPeriod(self.year, self.month)

    @property
    def fiscal_year(self) -> int:
        return self.year

    @property
    def period_number(self) -> int:
        return self.month

    @property
    def start_date(self) -> date:
        return self.period.start_date

    @property
    def end_date(self) -> date:
        return self.period.end_date

    def contains(self, value: date) -> bool:
        return self.period.contains(value)

    def assert_open_for_posting(self) -> None:
        if self.status is not FiscalPeriodStatus.OPEN:
            raise ClosedFiscalPeriodError(
                f"El periodo {self.period.code()} está "
                f"{'pre-cerrado' if self.status is FiscalPeriodStatus.SOFT_CLOSED else 'cerrado'}"
                "; no admite contabilizaciones")

    def soft_close(self, by: str | None = None) -> None:
        if self.status is not FiscalPeriodStatus.OPEN:
            raise PeriodStateError(f"No se pre-cierra un periodo {self.status.value}")
        self.status = FiscalPeriodStatus.SOFT_CLOSED
        self.soft_closed_at = _utcnow()
        self.soft_closed_by = by
        self.updated_at = self.soft_closed_at

    def close(self, closed_by: str) -> None:
        if self.status not in (FiscalPeriodStatus.OPEN, FiscalPeriodStatus.SOFT_CLOSED):
            raise PeriodStateError(f"No se cierra un periodo {self.status.value}")
        self.status = FiscalPeriodStatus.CLOSED
        self.closed_at = _utcnow()
        self.closed_by = closed_by
        self.updated_at = self.closed_at

    def reopen(self, reason: str, by: str | None = None) -> None:
        """Controlled reopening — requires an explicit audited reason."""
        if self.status not in (FiscalPeriodStatus.SOFT_CLOSED, FiscalPeriodStatus.CLOSED):
            raise PeriodStateError(f"No se reabre un periodo {self.status.value}")
        if not reason or not reason.strip():
            raise PeriodStateError("Reabrir un periodo exige el motivo")
        self.status = FiscalPeriodStatus.OPEN
        self.reopened_at = _utcnow()
        self.reopened_by = by
        self.reopen_reason = reason.strip()
        self.updated_at = self.reopened_at
