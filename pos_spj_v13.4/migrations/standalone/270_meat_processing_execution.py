"""270 — Procesamiento Cárnico ejecutable (Fase 10, 2026-09-19).

1. `processing_output_results`: el resultado por salida que pide el §13
   (esperado, real, diferencia, rendimiento %, costo repartido, lote origen y
   destino). La conciliación existente es por ORDEN; ésta es por corte.
2. Tolerancias de rendimiento en `configuraciones` — decisión del usuario: una
   tolerancia GLOBAL, igual para todos los cortes, configurable en Cárnico →
   Configuración. Valores iniciales: aviso 2 %, tolerancia 5 %, crítico 10 %
   (sobre la diferencia del corte contra lo esperado del despiece).
   `INSERT OR IGNORE`: si un administrador ya fijó un valor, no se pisa.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.meat_processing_schema import (
    create_meat_processing_output_results_schema,
)

logger = logging.getLogger("spj.migrations.270")

TOLERANCES = {
    "meat_processing.yield.warning_pct": ("2", "Rendimiento: aviso (%) de diferencia por corte"),
    "meat_processing.yield.tolerance_pct": ("5", "Rendimiento: tolerancia (%) por corte"),
    "meat_processing.yield.critical_pct": ("10", "Rendimiento: crítico (%) por corte"),
}


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='processing_orders'").fetchone():
        create_meat_processing_output_results_schema(conn)
    columnas = {r[1] for r in conn.execute("PRAGMA table_info(configuraciones)").fetchall()}
    if {"clave", "valor"} <= columnas:
        extra = [c for c in ("tipo", "grupo", "descripcion") if c in columnas]
        for clave, (valor, descripcion) in TOLERANCES.items():
            campos = ["clave", "valor", *extra]
            datos = {"clave": clave, "valor": valor, "tipo": "decimal",
                     "grupo": "produccion", "descripcion": descripcion}
            conn.execute(
                f"INSERT OR IGNORE INTO configuraciones ({','.join(campos)})"
                f" VALUES ({','.join('?' * len(campos))})", tuple(datos[c] for c in campos))
    conn.commit()
    logger.info("270: resultados por salida y tolerancias de rendimiento listos.")


up = run
