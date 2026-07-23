"""UnitOfMeasure — the canonical unit catalog (§15).

A configurable row (kg, g, lb, pieza, canal, caja, charola, bolsa, litro…), never
hardcoded in the UI. Each unit carries its dimension so conversions stay within a
family (weight↔weight, count↔count) unless a product-specific conversion bridges
them (e.g. 1 caja = 20 kg for a specific product).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidUnitOfMeasureError
from backend.domain.products.unit_enums import UnitDimension
from backend.shared.ids import new_uuid


@dataclass
class UnitOfMeasure:
    code: str
    name: str
    dimension: UnitDimension
    id: str = field(default_factory=new_uuid)
    active: bool = True

    def __post_init__(self) -> None:
        code = (self.code or "").strip().upper()
        if not code:
            raise InvalidUnitOfMeasureError("La unidad requiere un código")
        if not (self.name or "").strip():
            raise InvalidUnitOfMeasureError("La unidad requiere un nombre")
        if not isinstance(self.dimension, UnitDimension):
            try:
                self.dimension = UnitDimension(str(self.dimension))
            except ValueError as exc:
                raise InvalidUnitOfMeasureError(
                    f"Dimensión de unidad inválida: {self.dimension!r}") from exc
        object.__setattr__(self, "code", code)
