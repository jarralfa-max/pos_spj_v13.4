"""Quantity and Weight value objects (immutable, Decimal-only).

Meat/poultry inventory tracks pieces AND real weight simultaneously (§17), so a
movement line may carry both. Neither is derived from the other. Float is
rejected outright (REGLA CERO / §8).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.inventory.exceptions import InventoryDomainError


def _dec(value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en cantidades/pesos")
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:  # pragma: no cover - defensive
        raise InventoryDomainError(f"Cantidad inválida: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit: str = "PZA"

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _dec(self.value))
        if self.value < 0:
            raise InventoryDomainError("La cantidad no puede ser negativa")
        if not self.unit:
            raise InventoryDomainError("La cantidad requiere unidad")

    @property
    def is_zero(self) -> bool:
        return self.value == 0

    def add(self, other: "Quantity") -> "Quantity":
        self._same_unit(other)
        return Quantity(self.value + other.value, self.unit)

    def subtract(self, other: "Quantity") -> "Quantity":
        self._same_unit(other)
        return Quantity(self.value - other.value, self.unit)

    def _same_unit(self, other: "Quantity") -> None:
        if self.unit != other.unit:
            raise InventoryDomainError(
                f"Unidades incompatibles: {self.unit} vs {other.unit}")


@dataclass(frozen=True, slots=True)
class Weight:
    value: Decimal
    unit: str = "KG"

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _dec(self.value))
        if self.value < 0:
            raise InventoryDomainError("El peso no puede ser negativo")
        if not self.unit:
            raise InventoryDomainError("El peso requiere unidad")

    @property
    def is_zero(self) -> bool:
        return self.value == 0
