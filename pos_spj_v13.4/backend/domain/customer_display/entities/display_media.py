"""DisplayMedia — un archivo de imagen o video para la pantalla del cliente.

El contenido IMAGE/VIDEO guarda en `body` el id de este registro (§15: "No
almacenar ... rutas arbitrarias. Usar AssetReference"), nunca una ruta: el
archivo se copia a la carpeta de media que administra la aplicación y se
identifica por UUIDv7. Así un archivo movido o borrado en el escritorio de
alguien no rompe la pantalla, y la misma imagen subida dos veces (mismo hash)
es un solo registro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.shared.ids import new_uuid

#: Extensiones aceptadas por tipo. Las que Qt sabe mostrar sin códecs extra.
ALLOWED_EXTENSIONS = {
    "IMAGE": frozenset({".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}),
    "VIDEO": frozenset({".mp4", ".avi", ".wmv", ".mov", ".mkv"}),
}
#: Tope por tipo, en bytes: una pantalla de mostrador no necesita más, y un
#: archivo enorme se copiaría a cada respaldo de la instalación.
MAX_BYTES = {"IMAGE": 10 * 1024 * 1024, "VIDEO": 200 * 1024 * 1024}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DisplayMedia:
    id: str
    media_type: str
    original_name: str
    stored_name: str
    size_bytes: int
    sha256: str
    created_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, media_type: str, original_name: str, extension: str, size_bytes: int,
               sha256: str, created_by_user_id: str | None = None) -> "DisplayMedia":
        media_type = str(media_type).upper()
        if media_type not in ALLOWED_EXTENSIONS:
            raise CustomerDisplayInvalidValueError("Sólo se adjuntan imágenes o videos.")
        extension = extension.lower()
        if extension not in ALLOWED_EXTENSIONS[media_type]:
            permitidas = ", ".join(sorted(ALLOWED_EXTENSIONS[media_type]))
            raise CustomerDisplayInvalidValueError(
                f"Formato {extension or 'sin extensión'} no admitido para "
                f"{'imagen' if media_type == 'IMAGE' else 'video'}; usa {permitidas}.")
        if size_bytes <= 0:
            raise CustomerDisplayInvalidValueError("El archivo está vacío.")
        if size_bytes > MAX_BYTES[media_type]:
            raise CustomerDisplayInvalidValueError(
                f"El archivo pesa {size_bytes // (1024 * 1024)} MB; el máximo es "
                f"{MAX_BYTES[media_type] // (1024 * 1024)} MB.")
        media_id = new_uuid()
        return cls(id=media_id, media_type=media_type, original_name=original_name.strip(),
                   stored_name=f"{media_id}{extension}", size_bytes=int(size_bytes),
                   sha256=sha256, created_by_user_id=created_by_user_id)
