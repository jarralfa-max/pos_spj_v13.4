"""Money value object — Decimal-backed, currency-aware, no floats allowed."""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal

from backend.domain.finance.exceptions import CurrencyMismatchError, InvalidMoneyError

DEFAULT_CURRENCY = "MXN"
DEFAULT_DECIMAL_PLACES = 2
DEFAULT_ROUNDING = decimal.ROUND_HALF_UP


@dataclass(frozen=True, slots=True)
class Money:
    """Immutable monetary amount.

    ``amount`` is always quantized to ``decimal_places`` using ``rounding_mode``.
    Arithmetic and comparison require identical ``currency_code``; there are no
    implicit float conversions and no silent rounding beyond the declared scale.
    """

    amount: Decimal
    currency_code: str = DEFAULT_CURRENCY
    decimal_places: int = DEFAULT_DECIMAL_PLACES
    rounding_mode: str = DEFAULT_ROUNDING

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise InvalidMoneyError("Money must not be built from float; use str or Decimal")
        if not isinstance(self.amount, Decimal):
            raise InvalidMoneyError(f"Money.amount must be Decimal, got {type(self.amount).__name__}")
        if not self.currency_code or not self.currency_code.isalpha():
            raise InvalidMoneyError(f"Invalid currency_code: {self.currency_code!r}")
        if self.amount.is_nan() or self.amount.is_infinite():
            raise InvalidMoneyError("Money.amount must be a finite Decimal")
        quantized = self.amount.quantize(self._exponent(), rounding=self.rounding_mode)
        object.__setattr__(self, "amount", quantized)
        object.__setattr__(self, "currency_code", self.currency_code.upper())

    # ── constructors ──────────────────────────────────────────────────────
    @classmethod
    def from_string(cls, raw: str, currency_code: str = DEFAULT_CURRENCY,
                    decimal_places: int = DEFAULT_DECIMAL_PLACES) -> "Money":
        """Build Money from a decimal string like ``"125.40"`` (event payload format)."""
        try:
            value = Decimal(str(raw).strip())
        except (decimal.InvalidOperation, AttributeError, TypeError) as exc:
            raise InvalidMoneyError(f"Cannot parse monetary string: {raw!r}") from exc
        return cls(value, currency_code, decimal_places)

    @classmethod
    def zero(cls, currency_code: str = DEFAULT_CURRENCY,
             decimal_places: int = DEFAULT_DECIMAL_PLACES) -> "Money":
        return cls(Decimal("0"), currency_code, decimal_places)

    # ── arithmetic ────────────────────────────────────────────────────────
    def add(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return self._new(self.amount + other.amount)

    def subtract(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return self._new(self.amount - other.amount)

    def multiply(self, factor: Decimal | int | str) -> "Money":
        if isinstance(factor, float):
            raise InvalidMoneyError("Money.multiply must not receive float")
        return self._new(self.amount * Decimal(str(factor)))

    def negate(self) -> "Money":
        return self._new(-self.amount)

    def abs(self) -> "Money":
        return self._new(abs(self.amount))

    def __add__(self, other: "Money") -> "Money":
        return self.add(other)

    def __sub__(self, other: "Money") -> "Money":
        return self.subtract(other)

    def __neg__(self) -> "Money":
        return self.negate()

    # ── comparison ────────────────────────────────────────────────────────
    def __lt__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount >= other.amount

    # ── predicates ────────────────────────────────────────────────────────
    def is_zero(self) -> bool:
        return self.amount == Decimal("0")

    def is_positive(self) -> bool:
        return self.amount > Decimal("0")

    def is_negative(self) -> bool:
        return self.amount < Decimal("0")

    # ── serialization ─────────────────────────────────────────────────────
    def to_string(self) -> str:
        """Canonical decimal string for persistence and event payloads."""
        return format(self.amount, "f")

    def __str__(self) -> str:
        return f"{self.to_string()} {self.currency_code}"

    # ── helpers ───────────────────────────────────────────────────────────
    def _exponent(self) -> Decimal:
        return Decimal(1).scaleb(-self.decimal_places)

    def _new(self, amount: Decimal) -> "Money":
        return Money(amount, self.currency_code, self.decimal_places, self.rounding_mode)

    def _assert_same_currency(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise InvalidMoneyError(f"Expected Money, got {type(other).__name__}")
        if self.currency_code != other.currency_code:
            raise CurrencyMismatchError(
                f"Currency mismatch: {self.currency_code} vs {other.currency_code}"
            )
