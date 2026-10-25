"""332 — Auditoría directa de Finanzas (d9f2bca), 2026-10-10.

Lleva el esquema de Finanzas y el outbox de RR. HH. al contrato que exigen las
correcciones de la auditoría (ver docs/refactor/FIN-AUD_auditoria_d9f2bca.md):

* ``receivable_charges`` (F03): cada pago a crédito de una venta con su
  identidad estable; dos pagos de 10 y 20 suman 30 y repetir uno no cambia nada.
* ``expense_requests`` (F15): la solicitud de gasto deja de ser un compromiso
  anónimo; un reintento no vuelve a comprometer.
* ``finance_close_exceptions`` (F16): las diferencias materiales quedan
  guardadas por periodo y bloquean su cierre hasta resolverse o autorizarse.
* ``row_version`` en CxC, CxP, documentos y presupuestos (F18).
* matches de conciliación activos/revertidos con unicidad global (F07/F08).
* evidencia de ejecución del pago a proveedor (F13).
* intentos y último error en ``finance_outbox`` y ``hr_outbox`` (F21).

Sólo agrega; no reescribe datos. Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.332")


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    # FIN-ERP (2026-10-21): las tablas y columnas financieras de esta auditoría
    # viven ya en la definición born-clean (migración 117); aquí sólo queda RR. HH.
    agregadas: list[str] = []
    if _tabla(conn, "hr_outbox"):
        from backend.infrastructure.db.schema.hr_schema import upgrade_hr_schema
        agregadas += upgrade_hr_schema(conn)
    conn.commit()
    logger.info("332: esquema de Finanzas al contrato de la auditoría; columnas nuevas: %s",
                agregadas or "ninguna")


up = run
