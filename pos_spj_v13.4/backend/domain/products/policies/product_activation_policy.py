"""Product activation policy (§7, §35) — a product must be complete to go ACTIVE.

No se puede activar un producto incompleto cuando la policy exige revisión: unidad
base, categoría y —para cárnicos— especie son obligatorios. La lista de faltantes
alimenta también la alerta "producto incompleto" (§35).
"""

from __future__ import annotations

from backend.domain.products.entities.product import Product
from backend.domain.products.exceptions import ProductIncompleteError


def missing_fields(product: Product) -> list[str]:
    return product.missing_activation_data()


def validate_activation(product: Product) -> None:
    missing = missing_fields(product)
    if missing:
        raise ProductIncompleteError(
            "No se puede activar; faltan datos maestros: " + ", ".join(missing))
