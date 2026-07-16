"""ExchangeRate value object."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.finance.exceptions import FinanceDomainError, InvalidMoneyError
from backend.domain.finance.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class ExchangeRate:
    from_currency: str
    to_currency: str
    rate: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.rate, float):
            raise InvalidMoneyError("ExchangeRate.rate must not be float")
        if not isinstance(self.rate, Decimal) or self.rate <= 0:
            raise FinanceDomainError(f"Invalid exchange rate: {self.rate!r}")
        object.__setattr__(self, "from_currency", self.from_currency.upper())
        object.__setattr__(self, "to_currency", self.to_currency.upper())

    @classmethod
    def identity(cls, currency: str) -> "ExchangeRate":
        return cls(currency, currency, Decimal("1"))

    def convert(self, money: Money) -> Money:
        if money.currency_code != self.from_currency:
            raise FinanceDomainError(
                f"Rate {self.from_currency}->{self.to_currency} cannot convert {money.currency_code}"
            )
        return Money(money.amount * self.rate, self.to_currency, money.decimal_places)
