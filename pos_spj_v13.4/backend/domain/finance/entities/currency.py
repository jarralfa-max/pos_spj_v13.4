"""Currency and exchange-rate records (§24).

La moneda base es configurable (``FinanceSettings.base_currency_code``). Un
tipo de cambio tiene vigencia por fecha; una operación en moneda extranjera
usa el vigente a su fecha contable y guarda el que usó en cada línea.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.finance.exceptions import FinanceDomainError, InvalidMoneyError
from backend.domain.finance.value_objects.exchange_rate import ExchangeRate
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid

_ROUNDING_MODES = frozenset({decimal.ROUND_HALF_UP, decimal.ROUND_HALF_EVEN,
                             decimal.ROUND_DOWN, decimal.ROUND_UP})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Currency:
    id: str
    code: str
    name: str
    decimal_places: int = 2
    rounding_mode: str = decimal.ROUND_HALF_UP
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, decimal_places: int = 2,
               rounding_mode: str = decimal.ROUND_HALF_UP) -> "Currency":
        code = (code or "").strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise FinanceDomainError(f"Código de moneda inválido: {code!r} (ISO 4217)")
        if not 0 <= int(decimal_places) <= 4:
            raise FinanceDomainError("Los decimales de una moneda van de 0 a 4")
        if rounding_mode not in _ROUNDING_MODES:
            raise FinanceDomainError(f"Modo de redondeo no soportado: {rounding_mode}")
        if not (name or "").strip():
            raise FinanceDomainError("La moneda requiere nombre")
        return cls(id=new_uuid(), code=code, name=name.strip(),
                   decimal_places=int(decimal_places), rounding_mode=rounding_mode)

    def money(self, amount: Decimal | str) -> Money:
        if isinstance(amount, float):
            raise InvalidMoneyError("No se construye dinero desde float")
        return Money(Decimal(str(amount)), self.code, self.decimal_places, self.rounding_mode)


@dataclass(slots=True)
class ExchangeRateRecord:
    id: str
    from_currency: str
    to_currency: str
    rate: Decimal
    effective_date: date
    source: str = ""
    created_by: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, from_currency: str, to_currency: str, rate: Decimal | str,
               effective_date: date, *, source: str = "",
               created_by: str | None = None) -> "ExchangeRateRecord":
        if isinstance(rate, float):
            raise InvalidMoneyError("El tipo de cambio no se captura como float")
        value = ExchangeRate(from_currency, to_currency, Decimal(str(rate)))
        if value.from_currency == value.to_currency:
            raise FinanceDomainError("Un tipo de cambio relaciona dos monedas distintas")
        return cls(id=new_uuid(), from_currency=value.from_currency,
                   to_currency=value.to_currency, rate=value.rate,
                   effective_date=effective_date, source=(source or "").strip(),
                   created_by=created_by)

    def as_value(self) -> ExchangeRate:
        return ExchangeRate(self.from_currency, self.to_currency, self.rate)
