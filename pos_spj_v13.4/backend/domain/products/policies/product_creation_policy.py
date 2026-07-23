"""Product creation policy (§7) — the rules a product must satisfy to be born.

Prohibido crear un producto sin tipo, sin unidad base, o un producto cárnico sin
especie cuando aplique. La policy es pura: no toca persistencia; devuelve o lanza.
"""

from __future__ import annotations

from backend.domain.products.enums import MEAT_PRODUCT_TYPES, ProductType
from backend.domain.products.exceptions import (
    InvalidProductTypeError,
    ProductsDomainError,
    SpeciesRequiredError,
)


def validate_creation(
    *,
    product_type: ProductType,
    base_unit_id: str | None,
    species_id: str | None,
    sellable: bool,
    internal_only: bool,
) -> None:
    if not isinstance(product_type, ProductType):
        raise InvalidProductTypeError(f"Tipo de producto inválido: {product_type!r}")
    if not base_unit_id:
        raise ProductsDomainError("El producto requiere una unidad base (§7)")
    if product_type in MEAT_PRODUCT_TYPES and not species_id:
        raise SpeciesRequiredError(
            f"El tipo cárnico {product_type.value} requiere especie (§11)")
    if internal_only and sellable:
        raise ProductsDomainError(
            "Un producto interno (INTERNAL_ONLY) no puede ser vendible (§13)")
