"""Brand — catálogo plano de marcas de producto (P1-02).

Clasificación comercial: un producto puede referenciar una marca (``brand_id``). No
es jerárquica (a diferencia de categorías) ni lleva precio/existencia — sólo
identidad, código único y nombre. Identidad UUIDv7.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidBrandError
from backend.shared.ids import new_uuid


def normalize_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


@dataclass
class Brand:
    code: str
    name: str
    id: str = field(default_factory=new_uuid)
    description: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        code = (self.code or "").strip().upper()
        if not code:
            raise InvalidBrandError("La marca requiere un código")
        if not (self.name or "").strip():
            raise InvalidBrandError("La marca requiere un nombre")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "name", (self.name or "").strip())
        desc = (self.description or "").strip() or None
        object.__setattr__(self, "description", desc)

    @property
    def name_normalized(self) -> str:
        return normalize_name(self.name)
