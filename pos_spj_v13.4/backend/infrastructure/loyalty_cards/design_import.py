"""Safe import of external card-design source files into a LOY-18 canvas
declaration (LOY-19, master prompt §41-42: "importación con saneamiento y
validación de seguridad").

Deliberately narrow: this NEVER auto-converts arbitrary vector/raster
content into design elements (TEXT/IMAGE/QR/BARCODE/SHAPE — LOY-18's own
closed vocabulary). Doing that generically would mean executing rendering
logic against an attacker-controlled file, which is exactly what §41-42
prohibits. It only safely extracts CANVAS DIMENSIONS from a real, validated
file of a supported format — the human still populates the actual design
elements in the Studio (LOY-18) afterward.

Lives in `infrastructure/`, not `domain/`, because it depends on external
libraries (Pillow, defusedxml) — this repo's own layering rule (`domain/`
must stay framework-free).
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from backend.domain.loyalty_cards.exceptions import InvalidCardDesignSchemaError

_MM_PER_INCH = Decimal("25.4")
_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB — reject oversized uploads outright
_RASTER_FORMATS = frozenset({"PNG", "JPEG", "JPG"})
SUPPORTED_IMPORT_FORMATS = frozenset({"PNG", "JPEG", "SVG"})
# PDF: intentionally NOT supported — no safe PDF-parsing library is available
# in this environment (verified before writing this module); importing one
# is future infrastructure work, not something to fake here.


def import_canvas_dimensions(file_bytes: bytes, source_format: str, *, dpi: int = 300) -> dict:
    """Returns `{"width_mm": "...", "height_mm": "..."}` for a validated
    source file. Raises `InvalidCardDesignSchemaError` for anything
    oversized, malformed, mismatched, or containing disallowed content —
    never attempts to strip/repair a bad file, only accept-or-reject."""
    if not file_bytes:
        raise InvalidCardDesignSchemaError("El archivo está vacío")
    if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
        raise InvalidCardDesignSchemaError("El archivo excede el tamaño máximo permitido (10 MB)")
    if dpi <= 0:
        raise InvalidCardDesignSchemaError("dpi debe ser positivo")

    fmt = (source_format or "").strip().upper()
    if fmt in _RASTER_FORMATS:
        return _import_raster(file_bytes, declared_format=fmt, dpi=dpi)
    if fmt == "SVG":
        return _import_svg(file_bytes)
    if fmt == "PDF":
        raise InvalidCardDesignSchemaError(
            "Importación de PDF no soportada todavía — no hay un parser seguro "
            "disponible en este entorno")
    raise InvalidCardDesignSchemaError(f"Formato de importación no soportado: {source_format!r}")


_DECLARED_TO_ACTUAL = {"PNG": {"PNG"}, "JPEG": {"JPEG"}, "JPG": {"JPEG"}}


def _import_raster(file_bytes: bytes, *, declared_format: str, dpi: int) -> dict:
    from PIL import Image

    try:
        with Image.open(BytesIO(file_bytes)) as probe:
            probe.verify()
    except Exception as exc:  # Pillow raises various subclasses depending on the failure
        raise InvalidCardDesignSchemaError(f"El archivo no es una imagen válida: {exc}") from exc

    # verify() consumes the file object; re-open for a real read of size/format.
    with Image.open(BytesIO(file_bytes)) as img:
        width_px, height_px = img.size
        actual_format = img.format

    if actual_format not in ("PNG", "JPEG"):
        raise InvalidCardDesignSchemaError(
            f"El contenido real del archivo ({actual_format}) no coincide con un "
            "formato raster soportado")
    if actual_format not in _DECLARED_TO_ACTUAL.get(declared_format, set()):
        raise InvalidCardDesignSchemaError(
            f"El contenido real del archivo ({actual_format}) no coincide con el "
            f"formato declarado ({declared_format})")
    if width_px <= 0 or height_px <= 0:
        raise InvalidCardDesignSchemaError("Dimensiones de imagen inválidas")

    width_mm = (Decimal(width_px) / Decimal(dpi)) * _MM_PER_INCH
    height_mm = (Decimal(height_px) / Decimal(dpi)) * _MM_PER_INCH
    return {
        "width_mm": str(width_mm.quantize(Decimal("0.01"))),
        "height_mm": str(height_mm.quantize(Decimal("0.01"))),
    }


_DISALLOWED_SVG_TAGS = frozenset({"script", "foreignObject"})
_DISALLOWED_HREF_PREFIXES = ("http://", "https://", "javascript:", "data:text/html")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _import_svg(file_bytes: bytes) -> dict:
    from defusedxml.common import DefusedXmlException
    from defusedxml.ElementTree import fromstring

    try:
        root = fromstring(file_bytes)
    except DefusedXmlException as exc:
        raise InvalidCardDesignSchemaError(f"SVG rechazado por seguridad XML: {exc}") from exc
    except Exception as exc:
        raise InvalidCardDesignSchemaError(f"El archivo no es SVG válido: {exc}") from exc

    if _local_name(root.tag) != "svg":
        raise InvalidCardDesignSchemaError("El archivo no es un documento SVG")

    for element in root.iter():
        local_tag = _local_name(element.tag)
        if local_tag in _DISALLOWED_SVG_TAGS:
            raise InvalidCardDesignSchemaError(
                f"SVG contiene un elemento no permitido: <{local_tag}>")
        for attr_name, attr_value in element.attrib.items():
            local_attr = _local_name(attr_name)
            if local_attr.lower().startswith("on"):
                raise InvalidCardDesignSchemaError(
                    f"SVG contiene un atributo de evento no permitido: {local_attr}")
            if local_attr in ("href",) and str(attr_value).strip().lower().startswith(
                _DISALLOWED_HREF_PREFIXES
            ):
                raise InvalidCardDesignSchemaError(
                    "SVG contiene una referencia externa no permitida")

    return _svg_dimensions_mm(root)


def _svg_dimensions_mm(root) -> dict:
    view_box = root.attrib.get("viewBox")
    if view_box:
        parts = view_box.split()
        if len(parts) == 4:
            try:
                width = Decimal(parts[2])
                height = Decimal(parts[3])
            except Exception:
                width = height = None
            if width and height and width > 0 and height > 0:
                return {"width_mm": str(width), "height_mm": str(height)}
    raise InvalidCardDesignSchemaError(
        "No se pudo determinar el tamaño del SVG (se requiere un viewBox válido)")
