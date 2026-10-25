"""ForeignCurrencyAmount / BaseCurrencyAmount (§24).

Un importe en moneda extranjera sólo se convierte con un tipo de cambio
explícito; el resultado es un importe en moneda base. No hay conversión
implícita ni redondeo oculto: ``to_base`` redondea con la escala de la moneda
base y la diferencia acumulada de un asiento se contabiliza aparte.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.finance.exceptions import CurrencyMismatchError
from backend.domain.finance.value_objects.exchange_rate import ExchangeRate
from backend.domain.finance.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class BaseCurrencyAmount:
    money: Money


@dataclass(frozen=True, slots=True)
class ForeignCurrencyAmount:
    money: Money
    rate: ExchangeRate

    def __post_init__(self) -> None:
        if self.money.currency_code != self.rate.from_currency:
            raise CurrencyMismatchError(
                f"El tipo {self.rate.from_currency}->{self.rate.to_currency} no convierte "
                f"{self.money.currency_code}")

    def to_base(self, decimal_places: int = 2) -> BaseCurrencyAmount:
        return BaseCurrencyAmount(Money(self.money.amount * self.rate.rate,
                                        self.rate.to_currency, decimal_places))
