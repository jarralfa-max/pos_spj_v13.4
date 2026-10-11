"""Imágenes de producto en la carpeta de datos de la aplicación (PROD-21).

Antes la galería guardaba en ``product_images.uri`` la ruta que el usuario
elegía (su escritorio, una USB, Descargas): al mover o borrar ese archivo la
tarjeta del POS se quedaba sin imagen. Ahora se COPIA a
``AppPaths.product_images_dir`` con nombre UUIDv7, ya girada según EXIF y
reducida a un tamaño razonable para pantalla (una foto de celular de 4000 px no
debe cargarse en cada tarjeta). Mismo criterio que ``DisplayMediaStorage``.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.domain.products.exceptions import ProductImageProcessingError
from backend.shared.app_paths import AppPaths
from backend.shared.ids import new_uuid

#: Lado máximo del original guardado (sobra para la galería y el POS).
MAX_STORED_SIDE = 1600


class LocalProductImageStorage:
    def __init__(self, directory: Path | str | None = None) -> None:
        self._dir = (Path(directory) if directory
                     else AppPaths.from_environment().product_images_dir)

    @property
    def directory(self) -> Path:
        return self._dir

    def import_original(self, source_path: str) -> str:
        source = Path(source_path).expanduser()
        if not source.is_file():
            raise ProductImageProcessingError(f"No se encontró el archivo: {source}")
        try:
            with Image.open(source) as raw:
                image = ImageOps.exif_transpose(raw)
                image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise ProductImageProcessingError(
                f"El archivo no es una imagen válida: {source.name}") from exc
        has_alpha = image.mode in ("RGBA", "LA", "PA") or (
            image.mode == "P" and "transparency" in image.info)
        image = image.convert("RGBA" if has_alpha else "RGB")
        if max(image.size) > MAX_STORED_SIDE:
            image.thumbnail((MAX_STORED_SIDE, MAX_STORED_SIDE), Image.LANCZOS)
        self._dir.mkdir(parents=True, exist_ok=True)
        if has_alpha:
            target = self._dir / f"{new_uuid()}.png"
            image.save(target, "PNG", optimize=True)
        else:
            target = self._dir / f"{new_uuid()}.jpg"
            image.save(target, "JPEG", quality=90, optimize=True)
        return str(target)

    def new_processed_path(self) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        return str(self._dir / f"{new_uuid()}_sin_fondo.png")

    def is_local_file(self, uri: str) -> bool:
        return bool(uri) and Path(uri).is_file()

    def discard(self, uri: str | None) -> None:
        if not uri or not self._is_managed(uri):
            return
        try:
            Path(uri).unlink(missing_ok=True)
        except OSError:
            # Un archivo bloqueado (abierto en un visor) no debe tumbar la
            # operación ya confirmada; queda huérfano en la carpeta.
            import logging
            logging.getLogger("spj.products.media").warning(
                "No se pudo borrar la imagen %s", uri, exc_info=True)

    def _is_managed(self, uri: str) -> bool:
        try:
            return Path(uri).resolve().parent == self._dir.resolve()
        except OSError:
            return False
