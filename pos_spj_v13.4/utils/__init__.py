# utils/__init__.py — SPJ POS v13.1
"""Utilidades compartidas. Importar desde aquí para evitar duplicación."""
from utils.helpers import (
    formato_moneda,
    formato_kg,
    safe_float,
    safe_int,
    redondear_precio,
    fecha_hoy,
    fecha_hora_ahora,
    fecha_display,
    fecha_hora_display,
    dias_hasta,
)
from utils.operation_context import (
    generate_operation_id,
    set_operation_id,
    get_operation_id,
    clear_operation_id,
    now_iso,
)

__all__ = [
    "formato_moneda", "formato_kg", "safe_float", "safe_int",
    "redondear_precio", "fecha_hoy", "fecha_hora_ahora",
    "fecha_display", "fecha_hora_display", "dias_hasta",
    "generate_operation_id", "set_operation_id", "get_operation_id",
    "clear_operation_id", "now_iso",
]
