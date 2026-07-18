"""ColdChainRange — the allowed temperature band for a product/warehouse (§21).

Immutable, Decimal-only (temperatures may be negative — freezers). The warning
margin defines the WARNING band just outside the compliant [min, max] range.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.inventory.exceptions import InventoryDomainError


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en temperatura")
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class ColdChainRange:
    min_temp: Decimal
    max_temp: Decimal
    warning_margin: Decimal = Decimal("0")
    unit: str = "C"

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_temp", _dec(self.min_temp))
        object.__setattr__(self, "max_temp", _dec(self.max_temp))
        object.__setattr__(self, "warning_margin", _dec(self.warning_margin))
        if self.max_temp < self.min_temp:
            raise InventoryDomainError("max_temp no puede ser menor que min_temp")
        if self.warning_margin < 0:
            raise InventoryDomainError("El margen de advertencia no puede ser negativo")

    def is_compliant(self, temperature) -> bool:
        t = _dec(temperature)
        return self.min_temp <= t <= self.max_temp

    def is_within_warning(self, temperature) -> bool:
        t = _dec(temperature)
        return (self.min_temp - self.warning_margin) <= t <= (self.max_temp + self.warning_margin)
