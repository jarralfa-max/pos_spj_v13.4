"""Resolución de la fuente de LECTURA de ventas durante el corte.

Los lectores canónicos deben leer `v_ventas_unificada` /
`v_detalles_venta_unificada` (migraciones 256/257): son la única fuente que
contiene a la vez las ventas del POS —que nacen en el agregado `sales`— y las
que los escritores legacy siguen mandando a `ventas`.

Pero una base que todavía no aplicó esas migraciones no tiene las vistas, y un
`no such table` dejaría al servicio sin datos (o peor: los servicios de BI
atrapan la excepción y devolverían CERO en silencio). Por eso se resuelve la
fuente en tiempo de consulta, con respaldo a la tabla legacy — el mismo
comportamiento que había antes del corte, ni mejor ni peor.

Un solo sitio y no una copia por lector: la lección de `session_access.py` en
esta misma rama, donde la misma derivación duplicada traía el mismo error en
dos archivos.

DESAPARECE CON LAS VISTAS: cuando el ratchet
(`tests/architecture/test_sales_persistence_split_ratchet.py`) mida 0
escritores legacy, las vistas se reducen a `sales`/`sale_lines`, los lectores
pasan a nombrarlas directamente y este módulo sobra.
"""

from __future__ import annotations

UNIFIED_SALES_VIEW = "v_ventas_unificada"
UNIFIED_SALE_LINES_VIEW = "v_detalles_venta_unificada"

LEGACY_SALES_TABLE = "ventas"
LEGACY_SALE_LINES_TABLE = "detalles_venta"


def _exists(conn, name: str) -> bool:
    """Acepta tabla O vista: `type='table'` a secas filtraría las vistas y
    haría que el respaldo se activara siempre."""
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
            (name,),
        ).fetchone() is not None
    except Exception:
        return False


def sales_source(conn) -> str:
    """Nombre de relación para la CABECERA de venta."""
    return UNIFIED_SALES_VIEW if _exists(conn, UNIFIED_SALES_VIEW) else LEGACY_SALES_TABLE


def sale_lines_source(conn) -> str:
    """Nombre de relación para las LÍNEAS de venta."""
    return (UNIFIED_SALE_LINES_VIEW if _exists(conn, UNIFIED_SALE_LINES_VIEW)
            else LEGACY_SALE_LINES_TABLE)
