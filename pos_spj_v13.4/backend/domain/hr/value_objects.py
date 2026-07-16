"""Value objects for the canonical HR domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "MXN"

    def __post_init__(self) -> None:
        if self.amount < Decimal("0"):
            raise ValueError("money amount cannot be negative")


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("date range end cannot be before start")


@dataclass(frozen=True, slots=True)
class TimeRange:
    start: time
    end: time
    crosses_midnight: bool = False


@dataclass(frozen=True, slots=True)
class AuditStamp:
    created_at: datetime
    updated_at: datetime | None = None
