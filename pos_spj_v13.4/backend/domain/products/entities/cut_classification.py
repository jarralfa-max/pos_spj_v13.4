"""CutClassification — hierarchical meat cut catalog (§11).

Cuts form a tree per species: carcass → primary cut → secondary cut → portion.
Each node references its species and anatomical region, its level in the
hierarchy, and optionally its parent cut. A cut may not be its own parent, and a
child's level must sit strictly below its parent's (a PRIMARY cannot hang off a
PORTION). The tree is data, never hardcoded to one species.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.enums import LifecycleStatus
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.meat_enums import (
    BoneStatus,
    CutLevel,
    FatClass,
    cut_level_rank,
)
from backend.shared.ids import new_uuid


@dataclass
class CutClassification:
    species_id: str
    anatomical_region_id: str
    code: str
    name: str
    cut_level: CutLevel
    id: str = field(default_factory=new_uuid)
    bone_status: BoneStatus = BoneStatus.NOT_APPLICABLE
    fat_class: FatClass = FatClass.NOT_APPLICABLE
    quality_grade: str | None = None
    parent_cut_id: str | None = None
    status: LifecycleStatus = LifecycleStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.species_id:
            raise ProductsDomainError("El corte requiere especie (§11)")
        if not self.anatomical_region_id:
            raise ProductsDomainError("El corte requiere región anatómica (§7)")
        code = (self.code or "").strip().upper()
        if not code:
            raise ProductsDomainError("El corte requiere un código")
        if not (self.name or "").strip():
            raise ProductsDomainError("El corte requiere un nombre")
        if not isinstance(self.cut_level, CutLevel):
            self.cut_level = CutLevel(str(self.cut_level))
        if self.parent_cut_id and self.parent_cut_id == self.id:
            raise ProductsDomainError("Un corte no puede ser su propio padre")
        object.__setattr__(self, "code", code)

    def validate_under_parent(self, parent: "CutClassification") -> None:
        """A child cut must belong to the same species and sit below the parent."""
        if parent.id == self.id:
            raise ProductsDomainError("Un corte no puede ser su propio padre")
        if parent.species_id != self.species_id:
            raise ProductsDomainError(
                "El corte hijo debe pertenecer a la misma especie que el padre")
        if cut_level_rank(self.cut_level) <= cut_level_rank(parent.cut_level):
            raise ProductsDomainError(
                f"El nivel del corte ({self.cut_level.value}) debe estar por "
                f"debajo del padre ({parent.cut_level.value})")
