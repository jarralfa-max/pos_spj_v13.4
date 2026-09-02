"""OrderQuantity value object (immutable, Decimal-only). Mirrors
backend/domain/sales/value_objects/quantity.py's own `Quantity` exactly,
scoped to Pedidos/Delivery with its own exception type. Used for both
piece-counted quantities and catch-weight weights (§12: a `CustomerOrderLine`
tracks `requested_quantity`/`requested_weight`/`prepared_quantity`/
`prepared_weight`/`final_quantity`/`final_weight` as independent optional
values of this same shape — the full adjust/tolerance/approval policy layer
around them is ORD-10's scope, not this one).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.orders_delivery.exceptions import InvalidOrderQuantityError


def _dec(value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidOrderQuantityError("No se permite float en cantidades/pesos")
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:  # pragma: no cover - defensive
        raise InvalidOrderQuantityError(f"Cantidad/peso inválido: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class OrderQuantity:
    value: Decimal
    unit: str = "PZA"

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _dec(self.value))
        if self.value <= 0:
            raise InvalidOrderQuantityError("La cantidad/peso debe ser mayor a cero")
        if not self.unit:
            raise InvalidOrderQuantityError("La cantidad/peso requiere unidad")

    def add(self, other: "OrderQuantity") -> "OrderQuantity":
        self._same_unit(other)
        return OrderQuantity(self.value + other.value, self.unit)

    def _same_unit(self, other: "OrderQuantity") -> None:
        if self.unit != other.unit:
            raise InvalidOrderQuantityError(f"Unidades incompatibles: {self.unit} vs {other.unit}")
