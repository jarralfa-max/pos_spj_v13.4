"""Species — canonical animal-species catalog (§11).

A configurable row (never a hardcoded chicken-only list). Products of a meat type
must reference a species; anatomical regions and cuts hang off it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import ProductsDomainError
from backend.shared.ids import new_uuid


@dataclass
class Species:
    code: str
    name: str
    id: str = field(default_factory=new_uuid)
    active: bool = True

    def __post_init__(self) -> None:
        code = (self.code or "").strip().upper()
        if not code:
            raise ProductsDomainError("La especie requiere un código")
        if not (self.name or "").strip():
            raise ProductsDomainError("La especie requiere un nombre")
        object.__setattr__(self, "code", code)
