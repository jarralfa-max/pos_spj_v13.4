"""ProductCategory — nodo del árbol jerárquico de categorías de producto (P1-01).

Cada categoría tiene identidad UUIDv7, un código único, un nombre, y opcionalmente
un padre. La ruta materializada (``/id_raiz/.../id_propio/``) y la profundidad se
derivan del padre — no se capturan a mano — para consultas de subárbol y control de
ciclos/profundidad baratos. Sin precio ni existencia: es sólo clasificación.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidCategoryError
from backend.shared.ids import new_uuid


def normalize_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


@dataclass
class ProductCategory:
    code: str
    name: str
    id: str = field(default_factory=new_uuid)
    parent_id: str | None = None
    depth: int = 0
    path: str = ""
    sort_order: int = 0
    active: bool = True

    def __post_init__(self) -> None:
        code = (self.code or "").strip().upper()
        if not code:
            raise InvalidCategoryError("La categoría requiere un código")
        if not (self.name or "").strip():
            raise InvalidCategoryError("La categoría requiere un nombre")
        if self.depth < 0:
            raise InvalidCategoryError("La profundidad de la categoría no puede ser negativa")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "name", (self.name or "").strip())

    @property
    def name_normalized(self) -> str:
        return normalize_name(self.name)

    @property
    def is_root(self) -> bool:
        return self.parent_id is None
