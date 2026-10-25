"""Código automático de los catálogos de Productos (PROD-23).

Una sola regla para la vista previa del diálogo y para el alta: si el código
viene vacío se deriva del nombre (``catalog_code_policy``) y se garantiza que no
exista en su ámbito (las opciones son únicas por atributo; regiones y cortes,
por especie). El alta vuelve a resolverlo dentro de su transacción, así que la
vista previa nunca es una promesa: si otro usuario tomó el código entre tanto,
se asigna el siguiente libre.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.products.policies.catalog_code_policy import suggest_catalog_code


class CatalogCodeKind(str, Enum):
    CATEGORY = "CATEGORY"
    BRAND = "BRAND"
    ATTRIBUTE = "ATTRIBUTE"
    ATTRIBUTE_OPTION = "ATTRIBUTE_OPTION"   # ámbito: attribute_id
    SPECIES = "SPECIES"
    ANATOMICAL_REGION = "ANATOMICAL_REGION"  # ámbito: species_id
    CUT = "CUT"                              # ámbito: species_id


def _is_taken(connection, kind: CatalogCodeKind, scope_id: str | None):
    from backend.infrastructure.db.repositories.products.attribute_repository import (
        ProductAttributeRepository,
    )
    from backend.infrastructure.db.repositories.products.brand_repository import (
        ProductBrandRepository,
    )
    from backend.infrastructure.db.repositories.products.category_repository import (
        ProductCategoryRepository,
    )
    from backend.infrastructure.db.repositories.products.meat_classification_repository import (  # noqa: E501
        MeatClassificationRepository,
    )
    kind = CatalogCodeKind(kind)
    if kind is CatalogCodeKind.CATEGORY:
        return ProductCategoryRepository(connection).code_exists
    if kind is CatalogCodeKind.BRAND:
        return ProductBrandRepository(connection).code_exists
    if kind is CatalogCodeKind.ATTRIBUTE:
        return ProductAttributeRepository(connection).code_exists
    if kind is CatalogCodeKind.ATTRIBUTE_OPTION:
        repo = ProductAttributeRepository(connection)
        return lambda code: repo.option_code_exists(scope_id or "", code)
    meat = MeatClassificationRepository(connection)
    if kind is CatalogCodeKind.SPECIES:
        return meat.species_code_exists
    if kind is CatalogCodeKind.ANATOMICAL_REGION:
        return lambda code: meat.region_code_exists(scope_id or "", code)
    return lambda code: meat.cut_code_exists(scope_id or "", code)


def resolve_catalog_code(connection, kind: CatalogCodeKind, *, code: str | None,
                         name: str, scope_id: str | None = None) -> str:
    """El código escrito (en mayúsculas) o, si viene vacío, uno libre del nombre."""
    written = (code or "").strip().upper()
    if written:
        return written
    return suggest_catalog_code(name, _is_taken(connection, kind, scope_id))


class CatalogCodeSuggestionQueryService:
    """Vista previa del código mientras se escribe el nombre (no reserva nada)."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def suggest(self, kind: CatalogCodeKind | str, name: str, *,
                scope_id: str | None = None) -> str:
        if not (name or "").strip():
            return ""
        return resolve_catalog_code(self._conn, CatalogCodeKind(kind), code="",
                                    name=name, scope_id=scope_id)
