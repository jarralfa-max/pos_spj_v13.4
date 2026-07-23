"""Meat product classification policy (§11) — a meat product must be well-classified.

Prohibido: crear un producto cárnico sin especie; crear un corte sin clasificación
anatómica; clasificar contra una región de otra especie; o colgar un corte de un
padre de especie distinta o de nivel inferior/igual. La policy es pura.
"""

from __future__ import annotations

from backend.domain.products.entities.anatomical_region import AnatomicalRegion
from backend.domain.products.entities.cut_classification import CutClassification
from backend.domain.products.entities.species import Species
from backend.domain.products.enums import MEAT_PRODUCT_TYPES, ProductType
from backend.domain.products.exceptions import (
    ProductsDomainError,
    SpeciesRequiredError,
)


def requires_classification(product_type: ProductType) -> bool:
    return product_type in MEAT_PRODUCT_TYPES


def validate_region_species(region: AnatomicalRegion, species: Species) -> None:
    if region.species_id != species.id:
        raise ProductsDomainError(
            "La región anatómica no pertenece a la especie indicada")


def validate_product_classification(
    *,
    product_type: ProductType,
    species: Species | None,
    cut: CutClassification | None,
    region: AnatomicalRegion | None = None,
) -> None:
    """A meat product must carry species (and a coherent cut/region when given)."""
    if not requires_classification(product_type):
        return
    if species is None:
        raise SpeciesRequiredError(
            f"El tipo cárnico {product_type.value} requiere especie (§11)")
    if cut is not None:
        if cut.species_id != species.id:
            raise ProductsDomainError(
                "El corte no pertenece a la especie del producto")
        if region is not None:
            validate_region_species(region, species)
            if cut.anatomical_region_id != region.id:
                raise ProductsDomainError(
                    "El corte no corresponde a la región anatómica indicada")
