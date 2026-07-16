"""AccountingPeriod value object — a year/month pair with date containment."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from backend.domain.finance.exceptions import FinanceDomainError


@dataclass(frozen=True, slots=True)
class AccountingPeriod:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise FinanceDomainError(f"Invalid month: {self.month}")
        if not 2000 <= self.year <= 2200:
            raise FinanceDomainError(f"Invalid year: {self.year}")

    @classmethod
    def from_date(cls, value: date) -> "AccountingPeriod":
        return cls(value.year, value.month)

    @property
    def start_date(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def end_date(self) -> date:
        return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])

    def contains(self, value: date) -> bool:
        return self.start_date <= value <= self.end_date

    def next(self) -> "AccountingPeriod":
        if self.month == 12:
            return AccountingPeriod(self.year + 1, 1)
        return AccountingPeriod(self.year, self.month + 1)

    def code(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def __str__(self) -> str:
        return self.code()
