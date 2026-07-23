"""BundleComponent — one component line of a bundle version (§28).

A component product with a Decimal quantity. It may be optional (mix-and-match) or
substitutable (configurable combos). Quantity is strictly positive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import InvalidBundleError
from backend.shared.ids import new_uuid


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidBundleError("La cantidad del componente no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidBundleError(f"Cantidad inválida: {value!r}") from exc


@dataclass
class BundleComponent:
    component_product_id: str
    quantity: Decimal
    unit_id: str
    id: str = field(default_factory=new_uuid)
    version_id: str | None = None
    optional: bool = False
    substitutable: bool = False
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.component_product_id:
            raise InvalidBundleError("El componente del combo requiere producto")
        if not self.unit_id:
            raise InvalidBundleError("El componente del combo requiere unidad")
        self.quantity = _dec(self.quantity)
        if self.quantity <= 0:
            raise InvalidBundleError("La cantidad del componente debe ser positiva")
