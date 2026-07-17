"""Value objects for procurement (immutable, Decimal-only money)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal, InvalidOperation

from backend.domain.procurement.exceptions import InvalidMoneyError


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency_code: str = "MXN"

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise InvalidMoneyError("Money no acepta float; usa Decimal/str")
        try:
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        except (InvalidOperation, ValueError):
            raise InvalidMoneyError(f"Monto inválido: {self.amount!r}")

    @classmethod
    def zero(cls, currency_code: str = "MXN") -> "Money":
        return cls(Decimal("0"), currency_code)

    def is_negative(self) -> bool:
        return self.amount < 0

    def add(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount, self.currency_code)

    def to_string(self) -> str:
        return f"{self.amount.quantize(Decimal('0.01'))}"


@dataclass(frozen=True, slots=True)
class DocumentNumber:
    """Human code per document type: PREFIX-YYYY-NNNNNN (never replaces the UUID)."""

    prefix: str
    year: int
    sequence: int

    def __str__(self) -> str:
        return f"{self.prefix}-{self.year:04d}-{self.sequence:06d}"

    @classmethod
    def parse(cls, value: str) -> "DocumentNumber":
        prefix, year, seq = value.split("-")
        return cls(prefix, int(year), int(seq))


@dataclass(frozen=True, slots=True)
class Tolerance:
    """A percentage tolerance (e.g. 2 = 2%)."""

    percentage: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "percentage", Decimal(str(self.percentage)))
        if self.percentage < 0:
            raise InvalidMoneyError("La tolerancia no puede ser negativa")

    def within(self, expected: Decimal, actual: Decimal) -> bool:
        if expected == 0:
            return actual == 0
        deviation = abs(actual - expected) / abs(expected) * Decimal("100")
        return deviation <= self.percentage


@dataclass(frozen=True, slots=True)
class ReceivingWindow:
    """Allowed direct-purchase / receiving window (24h HH:mm)."""

    start: time
    end: time

    def allows(self, moment: time) -> bool:
        if self.start <= self.end:
            return self.start <= moment <= self.end
        # overnight window
        return moment >= self.start or moment <= self.end


@dataclass(frozen=True, slots=True)
class PurchaseLimit:
    """A configurable monetary limit (never hardcoded in UI).

    ``maximum_per_transaction`` caps a single operation; ``requires_approval_above``
    is the threshold at which a hot authorization is needed (may be lower than the
    hard cap). Zero/None means "no cap".
    """

    currency_code: str = "MXN"
    maximum_per_transaction: Decimal | None = None
    maximum_per_day: Decimal | None = None
    maximum_per_month: Decimal | None = None
    requires_approval_above: Decimal | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    def __post_init__(self) -> None:
        for field_name in ("maximum_per_transaction", "maximum_per_day",
                           "maximum_per_month", "requires_approval_above"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, Decimal(str(value)))

    def is_active(self, on_date: date) -> bool:
        if self.valid_from and on_date < self.valid_from:
            return False
        if self.valid_to and on_date > self.valid_to:
            return False
        return True
