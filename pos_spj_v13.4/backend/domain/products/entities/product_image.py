"""ProductImage — imagen de la galería de un producto (P1 imágenes).

Cada producto puede tener varias imágenes; exactamente una es la principal (la que
se muestra en catálogo/POS). El ``uri`` referencia el archivo (ruta local o URL); el
maestro no almacena binarios. Identidad UUIDv7.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidProductImageError
from backend.shared.ids import new_uuid


@dataclass
class ProductImage:
    product_id: str
    uri: str
    id: str = field(default_factory=new_uuid)
    alt_text: str | None = None
    is_primary: bool = False
    sort_order: int = 0

    def __post_init__(self) -> None:
        if not (self.product_id or "").strip():
            raise InvalidProductImageError("La imagen requiere producto")
        if not (self.uri or "").strip():
            raise InvalidProductImageError("La imagen requiere una referencia (uri)")
        object.__setattr__(self, "uri", self.uri.strip())
        alt = (self.alt_text or "").strip() or None
        object.__setattr__(self, "alt_text", alt)
