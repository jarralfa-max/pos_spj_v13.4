"""TemperatureRange — a Decimal storage/transport temperature band (§18).

Products declares the cold-chain band; Inventory (INV-9) records real readings and
raises excursions. Decimal-only (fridge setpoints like -18.0 °C matter), min ≤ max,
explicit unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import InvalidTemperatureRangeError


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidTemperatureRangeError("La temperatura no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidTemperatureRangeError(f"Temperatura inválida: {value!r}") from exc


@dataclass(frozen=True)
class TemperatureRange:
    minimum: Decimal
    maximum: Decimal
    unit: str = "C"

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum", _dec(self.minimum))
        object.__setattr__(self, "maximum", _dec(self.maximum))
        if not self.unit:
            raise InvalidTemperatureRangeError("El rango de temperatura requiere unidad")
        if self.minimum > self.maximum:
            raise InvalidTemperatureRangeError(
                "La temperatura mínima no puede exceder la máxima")

    def contains(self, temperature) -> bool:
        t = _dec(temperature)
        return self.minimum <= t <= self.maximum
