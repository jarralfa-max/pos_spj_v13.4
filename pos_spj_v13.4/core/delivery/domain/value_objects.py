from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit: str = "u"

    def __init__(self, value: float | int | str | Decimal, unit: str = "u") -> None:
        decimal_value = Decimal(str(value or 0))
        if decimal_value < 0:
            raise ValueError("La cantidad delivery no puede ser negativa.")
        object.__setattr__(self, "value", decimal_value)
        object.__setattr__(self, "unit", (unit or "u").strip().lower())

    def as_float(self) -> float:
        return float(self.value)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal

    def __init__(self, amount: float | int | str | Decimal) -> None:
        quantized = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    def as_float(self) -> float:
        return float(self.amount)


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lng: float

    def __post_init__(self) -> None:
        if not -90 <= float(self.lat) <= 90:
            raise ValueError("Latitud delivery fuera de rango.")
        if not -180 <= float(self.lng) <= 180:
            raise ValueError("Longitud delivery fuera de rango.")
