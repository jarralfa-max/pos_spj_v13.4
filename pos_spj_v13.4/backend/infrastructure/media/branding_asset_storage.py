"""Archivos de los logos de documentos impresos (comparativa de tickets, 2026-10-16).

Se COPIA el original a la carpeta de datos (nunca se apunta a la ruta que eligió
el usuario) y se genera un derivado para impresión térmica:

1. opcionalmente se quita el fondo con el MISMO removedor local de Productos
   (`EdgeConnectedBackgroundRemover`: el fondo es lo conectado al borde, así una
   letra blanca dentro del logo no se borra) con la tolerancia elegida;
2. la transparencia se aplana sobre BLANCO (en térmica lo transparente es papel);
3. se guarda en escala de grises; el rasterizado a 1 bit ocurre al imprimir, al
   ancho del papel.

El original queda intacto: cambiar la tolerancia o "conservar fondo" vuelve a
derivar desde él.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.shared.app_paths import AppPaths
from backend.shared.ids import new_uuid

MAX_SIDE = 1200
#: Un logo de más de 10 MB casi seguro no es un logo.
MAX_BYTES = 10 * 1024 * 1024


class BrandingAssetError(ValueError):
    """El archivo no sirve como logo; el mensaje es para la pantalla."""


class BrandingAssetStorage:
    def __init__(self, directory: Path | str | None = None) -> None:
        self._dir = Path(directory) if directory else AppPaths.from_environment().branding_dir

    @property
    def directory(self) -> Path:
        return self._dir

    def import_original(self, source_path: str) -> tuple[str, tuple[int, int]]:
        source = Path(source_path).expanduser()
        if not source.is_file():
            raise BrandingAssetError(f"No se encontró el archivo: {source}")
        if source.stat().st_size > MAX_BYTES:
            raise BrandingAssetError("El logo pesa más de 10 MB; usa una imagen más ligera")
        image = _open(source)
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / f"{new_uuid()}_original.png"
        image.save(target, "PNG", optimize=True)
        return str(target), image.size

    def derive_print_version(self, original_path: str, *, remove_background: bool,
                             tolerance: float | None = None, target_path: str | None = None
                             ) -> str:
        """El logo listo para térmica. `target_path` None = archivo nuevo en la
        biblioteca; para la vista previa se pasa una ruta temporal."""
        image = _open(Path(original_path))
        if remove_background:
            image = _remove_background(original_path, tolerance)
        flat = _flatten(image)
        target = Path(target_path) if target_path else self._dir / f"{new_uuid()}_impresion.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        flat.save(target, "PNG", optimize=True)
        return str(target)


def _open(path: Path) -> Image.Image:
    try:
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw)
            image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise BrandingAssetError(f"El archivo no es una imagen válida: {path.name}") from exc
    image = image.convert("RGBA")
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return image


def _remove_background(original_path: str, tolerance: float | None) -> Image.Image:
    import tempfile

    from backend.domain.products.exceptions import ProductImageProcessingError
    from backend.infrastructure.media.background_removal import EdgeConnectedBackgroundRemover

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "sin_fondo.png"
        try:
            EdgeConnectedBackgroundRemover(tolerance=tolerance, crop=True).remove_background(
                original_path, str(target))
        except ProductImageProcessingError as exc:
            raise BrandingAssetError(str(exc)) from exc
        with Image.open(target) as result:
            result.load()
            return result.convert("RGBA")


def _flatten(image: Image.Image) -> Image.Image:
    base = Image.new("RGBA", image.size, (255, 255, 255, 255))
    base.alpha_composite(image.convert("RGBA"))
    return ImageOps.autocontrast(base.convert("L"))
