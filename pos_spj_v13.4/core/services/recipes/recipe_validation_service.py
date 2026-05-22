# core/services/recipes/recipe_validation_service.py — FASE 2
"""
Pure domain validator for tipo_receta ↔ tipo_producto compatibility.

Strict mapping (from MASTER PROMPT FASE 2):
    COMBINACION  →  tipo_producto must be 'compuesto'
    SUBPRODUCTO  →  tipo_producto must be 'procesable'
    PRODUCCION   →  tipo_producto must be 'producido'

No DB access — receives values and validates them in-memory.
"""
from __future__ import annotations


# Canonical tipo_receta values
RECETA_COMBINACION = "COMBINACION"
RECETA_SUBPRODUCTO = "SUBPRODUCTO"
RECETA_PRODUCCION  = "PRODUCCION"

# Required tipo_producto for each tipo_receta
_REQUIRED_TIPO_PRODUCTO: dict[str, str] = {
    RECETA_COMBINACION: "compuesto",
    RECETA_SUBPRODUCTO: "procesable",
    RECETA_PRODUCCION:  "producido",
}

# Inverse: which tipo_receta is appropriate for each tipo_producto
_ALLOWED_RECETA_FOR_TIPO: dict[str, str] = {
    v: k for k, v in _REQUIRED_TIPO_PRODUCTO.items()
}

VALID_TIPOS_RECETA   = frozenset(_REQUIRED_TIPO_PRODUCTO)
VALID_TIPOS_PRODUCTO = frozenset(_REQUIRED_TIPO_PRODUCTO.values())


class RecetaTypeError(ValueError):
    """Raised when tipo_receta is incompatible with tipo_producto."""


class RecipeValidationService:
    """
    Stateless validator — instantiate once and reuse, or use class-methods.

    Usage::

        svc = RecipeValidationService()
        svc.validate_tipo_receta_producto("COMBINACION", "compuesto")   # OK
        svc.validate_tipo_receta_producto("COMBINACION", "simple")      # raises RecetaTypeError
        svc.infer_tipo_receta_from_producto("producido")                # returns "PRODUCCION"
    """

    # ── Validation ────────────────────────────────────────────────────────────

    @staticmethod
    def validate_tipo_receta_producto(tipo_receta: str, tipo_producto: str) -> None:
        """
        Validate that tipo_receta is compatible with tipo_producto.

        Raises RecetaTypeError if incompatible.
        """
        tipo_receta = (tipo_receta or "").upper().strip()
        tipo_producto = (tipo_producto or "").lower().strip()

        if tipo_receta not in VALID_TIPOS_RECETA:
            raise RecetaTypeError(
                f"tipo_receta inválido: '{tipo_receta}'. "
                f"Valores permitidos: {sorted(VALID_TIPOS_RECETA)}"
            )

        required = _REQUIRED_TIPO_PRODUCTO[tipo_receta]
        if tipo_producto != required:
            raise RecetaTypeError(
                f"tipo_receta '{tipo_receta}' requiere tipo_producto '{required}', "
                f"pero el producto tiene tipo_producto '{tipo_producto}'. "
                f"Actualice el tipo del producto antes de crear esta receta."
            )

    @staticmethod
    def validate_no_self_reference(product_id: int, component_id: int) -> None:
        """Raise RecetaTypeError if a product references itself as a component."""
        if product_id == component_id:
            raise RecetaTypeError(
                f"El producto id={product_id} no puede ser componente de sí mismo."
            )

    @staticmethod
    def validate_percentages(items: list[dict]) -> None:
        """
        For COMBINACION recipes: component percentages must sum to 100.

        items: list of dicts with key 'porcentaje' (float).
        """
        if not items:
            return
        total = sum(float(it.get("porcentaje", 0)) for it in items)
        if abs(total - 100.0) > 0.01:
            raise RecetaTypeError(
                f"Los porcentajes de la receta COMBINACION deben sumar 100 "
                f"(suma actual: {total:.2f})."
            )

    # ── Inference helpers ─────────────────────────────────────────────────────

    @staticmethod
    def infer_tipo_receta_from_producto(tipo_producto: str) -> str | None:
        """
        Return the canonical tipo_receta for a given tipo_producto, or None
        if the product type cannot have a recipe.
        """
        return _ALLOWED_RECETA_FOR_TIPO.get((tipo_producto or "").lower().strip())

    @staticmethod
    def infer_tipo_producto_from_receta(tipo_receta: str) -> str | None:
        """
        Return the required tipo_producto for a given tipo_receta, or None
        if tipo_receta is unknown.
        """
        return _REQUIRED_TIPO_PRODUCTO.get((tipo_receta or "").upper().strip())

    @staticmethod
    def product_can_have_recipe(tipo_producto: str) -> bool:
        """Return True if tipo_producto is allowed to have a recipe."""
        return (tipo_producto or "").lower().strip() in VALID_TIPOS_PRODUCTO
