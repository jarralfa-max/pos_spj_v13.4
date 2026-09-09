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


#: Marcadores que los lectores legacy dejan en su SQL para que el reescritor
#: los sustituya por la relación vigente. Se usan en `analytics_engine.py`,
#: cuyas 21 consultas viven en literales que ya interpolan otras cosas: pasar
#: cada una a f-string era el camino con más probabilidad de romper SQL en
#: silencio, así que la sustitución ocurre en un solo sitio.
#:
#: NO llevan llaves a propósito: un marcador `{...}` colisiona con los
#: f-strings y con `.format()` que esas mismas consultas ya usan — se
#: comprobó con un KeyError '_SRC_L' real en `product_profitability`.
SALES_PLACEHOLDER = "__SRC_H__"
SALE_LINES_PLACEHOLDER = "__SRC_L__"


class SalesSourceRewritingConnection:
    """Envoltura de conexión que resuelve los marcadores de relación de venta.

    Sólo toca el TEXTO del SQL, y sólo esos dos marcadores: no interpreta la
    consulta, no añade cláusulas y no cambia parámetros. Todo lo demás se
    delega intacto a la conexión real (`__getattr__`), incluidos `commit`,
    `row_factory` y los PRAGMA.

    Adaptador de transición (§4): desaparece cuando las vistas se reduzcan a
    `sales`/`sale_lines` y los lectores puedan nombrarlas directamente.
    """

    def __init__(self, connection) -> None:
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def _rewrite(self, sql):
        if not isinstance(sql, str):
            return sql
        if SALES_PLACEHOLDER in sql:
            sql = sql.replace(SALES_PLACEHOLDER, sales_source(self._connection))
        if SALE_LINES_PLACEHOLDER in sql:
            sql = sql.replace(
                SALE_LINES_PLACEHOLDER, sale_lines_source(self._connection))
        return sql

    def execute(self, sql, *args, **kwargs):
        return self._connection.execute(self._rewrite(sql), *args, **kwargs)

    def executemany(self, sql, *args, **kwargs):
        return self._connection.executemany(self._rewrite(sql), *args, **kwargs)

    def executescript(self, sql, *args, **kwargs):
        return self._connection.executescript(self._rewrite(sql), *args, **kwargs)
