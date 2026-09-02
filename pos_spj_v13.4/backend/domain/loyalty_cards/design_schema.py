"""Declarative, non-executable card design schema (LOY-18, master prompt
§34-36 — "Loyalty Card Studio").

§34-36's central security rule is unambiguous: a template's visual design
must be DECLARATIVE, never executable code. This module enforces it as a
closed allowlist — only known element types, only known fields per type,
and `TEXT` content may reference only a fixed vocabulary of `{{placeholder}}`
tokens. Anything outside that allowlist (an unknown key, a `<script>` tag,
an arbitrary expression, a new field nobody vetted) is REJECTED outright.
This module never attempts to sanitize or repair an invalid schema — it
fails closed, matching this pipeline's own "SQL seguro" discipline
(reject, don't patch, unsafe input) applied here to design markup instead.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from backend.domain.loyalty_cards.exceptions import InvalidCardDesignSchemaError

ELEMENT_TYPES = frozenset({"TEXT", "IMAGE", "QR", "BARCODE", "SHAPE"})
TEXT_ALIGNMENTS = frozenset({"LEFT", "CENTER", "RIGHT"})
IMAGE_SOURCES = frozenset({"STATIC", "LOGO", "CUSTOMER_PHOTO"})
QR_DATA_SOURCES = frozenset({"CARD_TOKEN"})
BARCODE_FORMATS = frozenset({"CODE128", "CODE39"})
BARCODE_DATA_SOURCES = frozenset({"CARD_NUMBER"})
SHAPE_TYPES = frozenset({"RECTANGLE", "CIRCLE", "LINE"})

# The ONLY placeholder tokens `TEXT.content` may reference — anything else
# (a formula, an arbitrary attribute lookup) is rejected.
ALLOWED_PLACEHOLDERS = frozenset({
    "customer_name", "card_number", "membership_tier", "points_balance",
    "expiry_date", "program_name",
})
# Matches ANY `{{...}}` span, not just well-formed-looking ones — deliberately
# broad so a malformed token like `{{__import__('os')}}` is CAUGHT (its inner
# text fails the identifier check below) instead of silently falling through
# unmatched and passing as ordinary text.
_PLACEHOLDER_RE = re.compile(r"\{\{(.*?)\}\}")
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidCardDesignSchemaError(message)


def _positive_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise InvalidCardDesignSchemaError(f"{field} debe ser numérico, no booleano")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise InvalidCardDesignSchemaError(f"{field} debe ser numérico")
    _require(parsed > 0, f"{field} debe ser positivo")
    return parsed


def _validate_text_content(content: object) -> None:
    _require(isinstance(content, str), "content debe ser texto")
    _require("<" not in content and ">" not in content,
              "content no puede contener marcado/etiquetas")
    for match in _PLACEHOLDER_RE.finditer(content):
        token = match.group(1).strip()
        _require(_IDENTIFIER_RE.match(token) is not None and token in ALLOWED_PLACEHOLDERS,
                  f"placeholder desconocido o inválido: {{{{{match.group(1)}}}}}")


def _validate_element(element: object) -> None:
    _require(isinstance(element, dict), "cada elemento debe ser un objeto JSON")
    element_type = element.get("type")
    _require(element_type in ELEMENT_TYPES, f"type de elemento inválido: {element_type!r}")
    _positive_decimal(element.get("x_mm"), "x_mm")
    _positive_decimal(element.get("y_mm"), "y_mm")
    _positive_decimal(element.get("width_mm"), "width_mm")
    _positive_decimal(element.get("height_mm"), "height_mm")

    if element_type == "TEXT":
        _validate_text_content(element.get("content", ""))
        if "align" in element:
            _require(element["align"] in TEXT_ALIGNMENTS, "align inválido")
    elif element_type == "IMAGE":
        _require(element.get("source") in IMAGE_SOURCES, "source de imagen inválido")
    elif element_type == "QR":
        _require(element.get("data_source") in QR_DATA_SOURCES, "data_source de QR inválido")
    elif element_type == "BARCODE":
        _require(element.get("format") in BARCODE_FORMATS, "format de barcode inválido")
        _require(element.get("data_source") in BARCODE_DATA_SOURCES,
                  "data_source de barcode inválido")
    elif element_type == "SHAPE":
        _require(element.get("shape_type") in SHAPE_TYPES, "shape_type inválido")


def validate_design_schema(design_schema_json: str) -> dict:
    """Parses and validates a design schema, returning the parsed dict.
    Raises `InvalidCardDesignSchemaError` on ANY structural or vocabulary
    violation."""
    _require(bool(design_schema_json) and design_schema_json.strip() != "",
              "design_schema_json es obligatorio")
    try:
        schema = json.loads(design_schema_json)
    except (json.JSONDecodeError, TypeError):
        raise InvalidCardDesignSchemaError("design_schema_json no es JSON válido")
    _require(isinstance(schema, dict), "el esquema debe ser un objeto JSON")

    canvas = schema.get("canvas")
    _require(isinstance(canvas, dict), "canvas es obligatorio")
    _positive_decimal(canvas.get("width_mm"), "canvas.width_mm")
    _positive_decimal(canvas.get("height_mm"), "canvas.height_mm")
    if "background_color" in canvas:
        _require(_HEX_COLOR_RE.match(str(canvas["background_color"])) is not None,
                  "canvas.background_color debe ser un color hex #RRGGBB")

    elements = schema.get("elements")
    _require(isinstance(elements, list), "elements debe ser una lista")
    for element in elements:
        _validate_element(element)

    return schema
