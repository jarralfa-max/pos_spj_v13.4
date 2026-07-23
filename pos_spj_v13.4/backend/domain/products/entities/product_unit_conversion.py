"""ProductUnitConversion — a Decimal, dated unit conversion (§16).

``1 from_unit = factor × to_unit``. The factor is always Decimal (never float),
strictly positive, with an explicit rounding scale and validity window. A
conversion may be global (``product_id`` None) or specific to one product (e.g.
1 caja = 20 kg only for this SKU). Catch-weight products whose real weight varies
must NOT rely on a fixed piece↔weight conversion — that is what CatchWeight is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import InvalidUnitConversionError
from backend.shared.ids import new_uuid


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidUnitConversionError("El factor de conversión no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidUnitConversionError(f"Factor inválido: {value!r}") from exc


@dataclass
class ProductUnitConversion:
    from_unit_id: str
    to_unit_id: str
    factor: Decimal
    id: str = field(default_factory=new_uuid)
    product_id: str | None = None          # None = conversión global
    rounding_scale: int = 6
    effective_from: str | None = None
    effective_to: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.from_unit_id or not self.to_unit_id:
            raise InvalidUnitConversionError("La conversión requiere unidades origen y destino")
        if self.from_unit_id == self.to_unit_id:
            raise InvalidUnitConversionError("Origen y destino no pueden ser la misma unidad")
        self.factor = _dec(self.factor)
        if self.factor <= 0:
            raise InvalidUnitConversionError("El factor de conversión debe ser positivo")
        if int(self.rounding_scale) < 0:
            raise InvalidUnitConversionError("rounding_scale no puede ser negativo")

    def convert(self, quantity: Decimal) -> Decimal:
        """Convert a quantity expressed in ``from_unit`` into ``to_unit``."""
        q = _dec(quantity)
        result = q * self.factor
        return result.quantize(Decimal(1).scaleb(-int(self.rounding_scale)))

    def inverse_factor(self) -> Decimal:
        return (Decimal(1) / self.factor)
