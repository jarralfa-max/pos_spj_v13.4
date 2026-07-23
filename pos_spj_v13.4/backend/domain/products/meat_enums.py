"""Meat classification enums for the products bounded context (§11).

PROD-3 adds the meat vocabulary. Deliberately multi-species — never chicken-only
(guardrail ``test_meat_products_are_not_chicken_only``). Species and anatomical
regions are *catalogs* (rows, configurable per species), so only the coarse
category / bone / fat / grade axes are enums; the concrete regions and cuts are
data.
"""

from __future__ import annotations

from enum import Enum


class MeatSpeciesCode(str, Enum):
    """Seed species (§11). The Species entity may add more rows at runtime."""

    POULTRY = "POULTRY"
    BOVINE = "BOVINE"
    PORCINE = "PORCINE"
    OVINE = "OVINE"
    CAPRINE = "CAPRINE"
    RABBIT = "RABBIT"
    FISH = "FISH"
    SEAFOOD = "SEAFOOD"
    OTHER = "OTHER"


class MeatCategory(str, Enum):
    """Coarse product family within a species (§11)."""

    LIVE = "LIVE"
    CARCASS = "CARCASS"
    HALF_CARCASS = "HALF_CARCASS"
    QUARTER = "QUARTER"
    BONE_IN = "BONE_IN"
    BONELESS = "BONELESS"
    OFFAL = "OFFAL"
    TRIM = "TRIM"
    GROUND = "GROUND"
    PROCESSED = "PROCESSED"
    MARINATED = "MARINATED"
    FROZEN = "FROZEN"
    CHILLED = "CHILLED"
    COOKED = "COOKED"
    BY_PRODUCT = "BY_PRODUCT"
    WASTE = "WASTE"


class BoneStatus(str, Enum):
    BONE_IN = "BONE_IN"
    BONELESS = "BONELESS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FatClass(str, Enum):
    LEAN = "LEAN"
    MEDIUM = "MEDIUM"
    FATTY = "FATTY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CutLevel(str, Enum):
    """Where a cut sits in the disassembly hierarchy (§11).

    canal → corte primario → corte secundario → porcionado.
    """

    CARCASS = "CARCASS"
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    PORTION = "PORTION"


# Orden jerárquico: un corte hijo no puede tener un nivel superior o igual al padre
# cuando el padre ya es una hoja. Se usa en la policy de clasificación.
_CUT_LEVEL_ORDER = {
    CutLevel.CARCASS: 0,
    CutLevel.PRIMARY: 1,
    CutLevel.SECONDARY: 2,
    CutLevel.PORTION: 3,
}


def cut_level_rank(level: CutLevel) -> int:
    return _CUT_LEVEL_ORDER[level]
