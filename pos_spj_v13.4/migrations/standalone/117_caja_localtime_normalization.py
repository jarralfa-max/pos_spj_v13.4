# migrations/standalone/117_caja_localtime_normalization.py
"""
117 — Normaliza a hora local los timestamps de caja escritos en UTC.

Bug (Caja en ceros): turnos_caja.fecha_apertura y movimientos_caja.fecha se
escribían con datetime('now') de SQLite (UTC) mientras ventas.fecha usa la
hora local del POS (datetime.now() de Python). En husos al oeste de UTC la
apertura quedaba horas "en el futuro": el filtro `ventas.fecha >=
fecha_apertura` no encontraba NINGUNA venta → KPIs de caja en 0 y efectivo
esperado del corte Z en 0.

El código ya escribe hora local; esta migración remienda las filas existentes
cuyo timestamp quedó en el futuro local (firma inequívoca de UTC en huso
negativo). Idempotente: tras convertir, ninguna fila queda en el futuro.
Solo toca turnos ABIERTOS (los cerrados son historial y no alimentan cálculo).
"""
from __future__ import annotations

import sqlite3

DESCRIPTION = "Hora local en fecha_apertura de turnos abiertos y movimientos de caja"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def run(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "turnos_caja"):
        conn.execute(
            """UPDATE turnos_caja
               SET fecha_apertura = datetime(fecha_apertura, 'localtime')
               WHERE estado = 'abierto'
                 AND fecha_apertura > datetime('now', 'localtime')"""
        )
    if _table_exists(conn, "movimientos_caja"):
        conn.execute(
            """UPDATE movimientos_caja
               SET fecha = datetime(fecha, 'localtime')
               WHERE fecha > datetime('now', 'localtime')"""
        )
    conn.commit()
