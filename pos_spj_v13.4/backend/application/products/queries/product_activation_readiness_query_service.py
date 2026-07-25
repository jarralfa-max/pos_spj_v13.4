"""ProductActivationReadinessQueryService (P0-05) — faltantes antes de activar.

La UI muestra la lista de datos maestros faltantes antes de permitir "Activar". Usa
los invariantes de la entidad `Product` (`missing_activation_data`) más reglas de
capacidad (vendible/interno) para explicar por qué un producto no puede activarse.
Read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.enums import MEAT_PRODUCT_TYPES, ProductType


@dataclass(frozen=True)
class ActivationReadiness:
    ready: bool
    missing: list[str] = field(default_factory=list)


_LABELS = {
    "base_unit_id": "Unidad base",
    "category_id": "Categoría",
    "species_id": "Especie (producto cárnico)",
    "sellable_unit": "Unidad válida para venta",
    "internal_conflict": "Interno no puede ser vendible",
}


class ProductActivationReadinessQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def readiness(self, product_id: str) -> ActivationReadiness:
        row = self._conn.execute(
            "SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if row is None:
            return ActivationReadiness(False, ["El producto no existe"])
        r = dict(row)
        missing: list[str] = []
        if not r.get("base_unit_id"):
            missing.append(_LABELS["base_unit_id"])
        if not r.get("category_id"):
            missing.append(_LABELS["category_id"])
        is_meat = ProductType(r["product_type"]) in MEAT_PRODUCT_TYPES
        if is_meat and not r.get("species_id"):
            missing.append(_LABELS["species_id"])
        if r.get("internal_only") and r.get("sellable"):
            missing.append(_LABELS["internal_conflict"])
        return ActivationReadiness(ready=not missing, missing=missing)
