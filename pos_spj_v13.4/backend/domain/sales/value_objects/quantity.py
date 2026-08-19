"""Quantity value object (immutable, Decimal-only). Mirrors
backend/domain/inventory/value_objects/quantity.py's own `Quantity`, scoped
to Sales/POS with its own exception type. Weight-based catch-weight capture
(scale hardware, master prompt §19) is POS-12 territory — this VO only
carries whatever Decimal quantity+unit a SaleLine was given, regardless of
source.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.sales.exceptions import InvalidQuantityError


def _dec(value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidQuantityError("No se permite float en cantidades")
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:  # pragma: no cover - defensive
        raise InvalidQuantityError(f"Cantidad inválida: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit: str = "PZA"

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _dec(self.value))
        if self.value <= 0:
            raise InvalidQuantityError("La cantidad debe ser mayor a cero")
        if not self.unit:
            raise InvalidQuantityError("La cantidad requiere unidad")

    def add(self, other: "Quantity") -> "Quantity":
        self._same_unit(other)
        return Quantity(self.value + other.value, self.unit)

    def _same_unit(self, other: "Quantity") -> None:
        if self.unit != other.unit:
            raise InvalidQuantityError(f"Unidades incompatibles: {self.unit} vs {other.unit}")
