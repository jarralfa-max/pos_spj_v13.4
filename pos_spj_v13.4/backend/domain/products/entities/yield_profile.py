"""YieldProfile — the technical output expectation of a process input (§23).

Bound to an input product (a carcass, an animal, a raw material) and a species,
it declares what outputs to expect (cuts, offal, fat, bone, skin, by-products,
waste) through its versions. Multi-species by construction — never chicken-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import YieldProfileInvalidError
from backend.shared.ids import new_uuid


@dataclass
class YieldProfile:
    input_product_id: str
    name: str
    id: str = field(default_factory=new_uuid)
    species_id: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.input_product_id:
            raise YieldProfileInvalidError("El perfil de rendimiento requiere producto de entrada")
        if not (self.name or "").strip():
            raise YieldProfileInvalidError("El perfil de rendimiento requiere un nombre")
