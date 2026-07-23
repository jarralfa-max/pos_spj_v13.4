"""AnatomicalRegion — species-scoped anatomical region catalog (§11).

Configurable per species (a bovine LOIN is not a poultry BREAST). A cut
classification references its region; the region references its species.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import ProductsDomainError
from backend.shared.ids import new_uuid


@dataclass
class AnatomicalRegion:
    species_id: str
    code: str
    name: str
    id: str = field(default_factory=new_uuid)
    active: bool = True

    def __post_init__(self) -> None:
        if not self.species_id:
            raise ProductsDomainError("La región anatómica requiere especie")
        code = (self.code or "").strip().upper()
        if not code:
            raise ProductsDomainError("La región anatómica requiere un código")
        if not (self.name or "").strip():
            raise ProductsDomainError("La región anatómica requiere un nombre")
        object.__setattr__(self, "code", code)
