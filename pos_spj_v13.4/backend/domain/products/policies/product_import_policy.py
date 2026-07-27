"""Política de validación de filas de importación (pura).

Valida la estructura mínima de una fila mapeada antes de crear el producto: nombre,
tipo (de la lista canónica) y unidad base obligatorios; el código es opcional (si va
vacío, el alta lo genera automáticamente). No toca persistencia.
"""

from __future__ import annotations

from backend.domain.products.enums import ProductType

_REQUIRED = ("name", "product_type", "base_unit_id")


def validate_import_row(row: dict) -> tuple[bool, str | None]:
    """Devuelve (válida, error). ``error`` es None cuando la fila es válida."""
    missing = [f for f in _REQUIRED if not str(row.get(f) or "").strip()]
    if missing:
        return False, f"Faltan campos: {', '.join(missing)}"
    try:
        ProductType(str(row["product_type"]).strip())
    except ValueError:
        return False, f"Tipo de producto inválido: {row.get('product_type')!r}"
    return True, None
