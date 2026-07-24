"""Money — a Decimal amount with a currency (PRC-2).

The single money value object for the pricing/costing context. Amounts are always
Decimal (float is rejected), rounded to the currency's minor unit; arithmetic
requires matching currencies. Prices are non-negative; a signed variant is allowed
for deltas via ``allow_negative``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from backend.domain.pricing.exceptions import (
    CurrencyMismatchError,
    InvalidMoneyError,
)

_QUANT = Decimal("0.0001")   # 4 decimales internos (precios por kilo, etc.)


def _to_decimal(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidMoneyError("El monto no puede ser float; use Decimal/str")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidMoneyError(f"Monto inválido: {value!r}") from exc


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "MXN"
    allow_negative: bool = False

    def __post_init__(self) -> None:
        amount = _to_decimal(self.amount).quantize(_QUANT, rounding=ROUND_HALF_UP)
        if not self.currency or len(self.currency) != 3:
            raise InvalidMoneyError("La moneda debe ser un código ISO de 3 letras")
        if amount < 0 and not self.allow_negative:
            raise InvalidMoneyError("El monto no puede ser negativo")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", self.currency.upper())

    # ── operaciones ───────────────────────────────────────────────────────
    def _check(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Monedas distintas: {self.currency} vs {other.currency}")

    def add(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency, allow_negative=True)

    def subtract(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency, allow_negative=True)

    def multiply(self, factor) -> "Money":
        return Money(self.amount * _to_decimal(factor), self.currency,
                     allow_negative=self.allow_negative)

    def is_zero(self) -> bool:
        return self.amount == 0

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    @classmethod
    def zero(cls, currency: str = "MXN") -> "Money":
        return cls(Decimal("0"), currency)
