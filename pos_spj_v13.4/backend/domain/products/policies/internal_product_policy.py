"""Internal product policy (§13) — the rules for non-sellable internal products.

An internal product (canal refrigerada, carne deshuesada sin empacar, mezcla para
hamburguesa, lote marinado, producto en cuarentena):
  - no aparece en POS ni en e-commerce;
  - puede tener inventario, costo, lote y calidad;
  - puede ser input u output de una receta;
  - no es vendible.
Convertir una etapa en otra que sea una transformación real exige un producto
distinto y una relación técnica explícita — nunca duplicar identidad por etapa.
"""

from __future__ import annotations

from backend.domain.products.entities.product import Product
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.internal_enums import InternalStage


def validate_internal_product(product: Product) -> None:
    """An internal product must be non-sellable and non-POS (§13)."""
    if not product.is_internal:
        return
    if product.sellable:
        raise ProductsDomainError(
            "Un producto interno no puede ser vendible (§13)")
    if product.is_visible_in_pos():
        raise ProductsDomainError(
            "Un producto interno no puede ser visible en POS (§13)")


def is_transformation(from_stage: InternalStage, to_stage: InternalStage) -> bool:
    """Whether moving between two stages is a real transformation (§13).

    A real transformation (WIP → semi-finished → finished) must be modeled as a
    distinct product with an explicit technical relationship, not a mutated
    identity. Same stage, or NONE on either side (first entering the internal
    pipeline, or leaving it, is a reclassification — not yet a physical
    transformation), is not a transformation. Between any two DIFFERENT
    non-NONE stages is always a real transformation.
    """
    if from_stage == to_stage:
        return False
    if InternalStage.NONE in (from_stage, to_stage):
        return False
    return True
