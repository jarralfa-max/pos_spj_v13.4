"""CuttingScheme — a species-specific disassembly plan (§24).

Bound to an input product (a carcass, a quarter) and a species, at a cut level
(carcass → primary → secondary → portion). Several schemes may exist per plant/
species. The concrete outputs live in its versions. Multi-species by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import CuttingSchemeInvalidError
from backend.domain.products.meat_enums import CutLevel
from backend.shared.ids import new_uuid


@dataclass
class CuttingScheme:
    input_product_id: str
    species_id: str
    name: str
    id: str = field(default_factory=new_uuid)
    cut_level: CutLevel = CutLevel.PRIMARY
    active: bool = True

    def __post_init__(self) -> None:
        if not self.input_product_id:
            raise CuttingSchemeInvalidError("El esquema requiere producto de entrada")
        if not self.species_id:
            raise CuttingSchemeInvalidError("El esquema de despiece requiere especie (§24)")
        if not (self.name or "").strip():
            raise CuttingSchemeInvalidError("El esquema requiere un nombre")
        if not isinstance(self.cut_level, CutLevel):
            self.cut_level = CutLevel(str(self.cut_level))
