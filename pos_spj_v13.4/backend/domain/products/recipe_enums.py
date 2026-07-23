"""Recipe / BOM enums for the products bounded context (§21, §22, §23).

PROD-9. A recipe is a structure of transformation; its type says *what kind*
(sales explosion, production BOM, disassembly/cutting yield, formula, marination,
grinding, mixing…). Every recipe, cutting scheme and yield profile is versioned
(§22). Recipe outputs carry an output role shared with yield profiles (§23).
"""

from __future__ import annotations

from enum import Enum


class RecipeType(str, Enum):
    SALES_EXPLOSION = "SALES_EXPLOSION"     # descompone un producto virtual al vender
    PRODUCTION_BOM = "PRODUCTION_BOM"       # consume componentes al producir
    PROCESSING_RECIPE = "PROCESSING_RECIPE"
    PACKAGING_BOM = "PACKAGING_BOM"
    DISASSEMBLY = "DISASSEMBLY"             # una entrada → múltiples outputs
    CUTTING_YIELD = "CUTTING_YIELD"
    FORMULA = "FORMULA"
    MARINATION = "MARINATION"
    GRINDING = "GRINDING"
    MIXING = "MIXING"


class RecipeVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    INACTIVE = "INACTIVE"


# Estados en los que una versión es inmutable (§22): no se modifica, se versiona.
IMMUTABLE_VERSION_STATES = frozenset({
    RecipeVersionStatus.APPROVED,
    RecipeVersionStatus.ACTIVE,
    RecipeVersionStatus.SUPERSEDED,
})


class OutputType(str, Enum):
    """Role of a recipe/yield output (§23)."""

    MAIN_PRODUCT = "MAIN_PRODUCT"
    CO_PRODUCT = "CO_PRODUCT"
    BY_PRODUCT = "BY_PRODUCT"
    WASTE = "WASTE"
    LOSS = "LOSS"


# Tipos de receta que producen múltiples salidas (§21).
MULTI_OUTPUT_TYPES = frozenset({
    RecipeType.DISASSEMBLY,
    RecipeType.CUTTING_YIELD,
})
