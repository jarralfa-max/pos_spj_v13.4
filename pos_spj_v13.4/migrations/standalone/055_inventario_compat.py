"""Migración 055 — compatibilidad de inventario legado.

Garantiza que exista un objeto `inventario` para módulos legacy que aún
consultan esa tabla (p.ej. ForecastEngine y validación fail-fast).
"""

import logging

logger = logging.getLogger("spj.migrations.055")


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _view_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def run(conn):
    # Si ya existe tabla inventario, no tocarla.
    if _table_exists(conn, "inventario"):
        logger.info("055: tabla inventario ya existe; sin cambios.")
        return

    # Si existe una vista previa corrupta/obsoleta, la reemplazamos.
    if _view_exists(conn, "inventario"):
        conn.execute("DROP VIEW inventario")

    # Compatibilidad de lectura sobre inventario_actual.
    conn.execute(
        """
        CREATE VIEW inventario AS
        SELECT
            producto_id,
            sucursal_id,
            cantidad AS existencia,
            ultima_actualizacion
        FROM inventario_actual
        """
    )
    conn.commit()
    logger.info("055: vista inventario creada (compatibilidad legacy).")


up = run
