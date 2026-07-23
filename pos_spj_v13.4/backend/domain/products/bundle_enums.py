"""Bundle / combo / kit enums for the products bounded context (§28).

PROD-13. Products defines the composition; Inventory/Production execute the
assembly. A virtual bundle is exploded at sale time (no stock of its own); a
stocked kit is assembled beforehand and carries its own stock.
"""

from __future__ import annotations

from enum import Enum


class BundleType(str, Enum):
    VIRTUAL_BUNDLE = "VIRTUAL_BUNDLE"       # se descompone al vender (sin stock propio)
    STOCKED_KIT = "STOCKED_KIT"             # se arma previamente (stock propio)
    FIXED_COMBO = "FIXED_COMBO"
    CONFIGURABLE_COMBO = "CONFIGURABLE_COMBO"
    MIX_AND_MATCH = "MIX_AND_MATCH"
    ASSORTED_PACKAGE = "ASSORTED_PACKAGE"
    GIFT_SET = "GIFT_SET"
    MEAT_BOX = "MEAT_BOX"


# Tipos que mantienen stock propio (se arman antes de vender, §28).
STOCKED_TYPES = frozenset({BundleType.STOCKED_KIT})

# Tipos que se descomponen al vender (no mantienen stock del bundle).
VIRTUAL_TYPES = frozenset({
    BundleType.VIRTUAL_BUNDLE,
    BundleType.FIXED_COMBO,
    BundleType.CONFIGURABLE_COMBO,
    BundleType.MIX_AND_MATCH,
    BundleType.ASSORTED_PACKAGE,
    BundleType.GIFT_SET,
    BundleType.MEAT_BOX,
})
