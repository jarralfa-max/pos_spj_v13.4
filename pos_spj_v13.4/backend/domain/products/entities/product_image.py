"""ProductImage — imagen de la galería de un producto (P1 imágenes).

Cada producto puede tener varias imágenes; exactamente una es la principal (la que
se muestra en catálogo/POS). El ``uri`` referencia el archivo (ruta local o URL); el
maestro no almacena binarios. Identidad UUIDv7.

PROD-21 (quitar fondo): ``uri`` es SIEMPRE lo que se muestra. Al quitar el fondo,
``uri`` pasa a la versión recortada (PNG con transparencia) y ``source_uri``
conserva el original para poder restaurarlo; nunca se quita el fondo dos veces
sobre un resultado ya procesado.
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
    source_uri: str | None = None
    background_removed: bool = False

    def __post_init__(self) -> None:
        if not (self.product_id or "").strip():
            raise InvalidProductImageError("La imagen requiere producto")
        if not (self.uri or "").strip():
            raise InvalidProductImageError("La imagen requiere una referencia (uri)")
        object.__setattr__(self, "uri", self.uri.strip())
        alt = (self.alt_text or "").strip() or None
        object.__setattr__(self, "alt_text", alt)
        if self.background_removed and not (self.source_uri or "").strip():
            raise InvalidProductImageError(
                "Una imagen sin fondo debe conservar su original")

    @property
    def original_uri(self) -> str:
        """El archivo del que se parte para procesar: el original si existe."""
        return self.source_uri or self.uri

    def mark_background_removed(self, processed_uri: str) -> None:
        if self.background_removed:
            raise InvalidProductImageError("La imagen ya no tiene fondo")
        if not (processed_uri or "").strip():
            raise InvalidProductImageError("Falta la imagen procesada")
        self.source_uri = self.uri
        self.uri = processed_uri.strip()
        self.background_removed = True

    def restore_original(self) -> str:
        """Vuelve al original; devuelve la referencia procesada que se descarta."""
        if not self.background_removed or not self.source_uri:
            raise InvalidProductImageError("La imagen conserva su fondo original")
        processed = self.uri
        self.uri = self.source_uri
        self.source_uri = None
        self.background_removed = False
        return processed
