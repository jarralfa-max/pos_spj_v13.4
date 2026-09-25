"""274 — Procesamiento deja de tener, por ROL, el permiso de registrar
decisiones de calidad (decisión del usuario, 2026-09-24).

La 271 sembró `PRODUCCION.calidad.registrar_decision` a los roles de
producción. Desde la auditoría profunda ese permiso sólo lo ejerce la
concesión de Calidad (`QUALITY_CALLBACK_GRANT`, en nombre del inspector que
decidió) y `RecordQualityDecisionUseCase` exige que la decisión exista en
Calidad: en un rol ya no permitía nada, sólo confundía. Se retira de TODOS
los roles; decidir calidad es `CALIDAD.inspeccion.decidir` (migración 273).

Idempotente. Si alguien lo vuelve a conceder a mano, la regla de negocio
(sólo decisiones que existen en Calidad) sigue vigente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.274")

MODULO, ACCION = "PRODUCCION", "calidad.registrar_decision"


def run(conn) -> None:
    existe = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rol_permisos'").fetchone()
    if existe is None:
        logger.info("274: sin tabla de permisos por rol; nada que hacer.")
        return
    cur = conn.execute("DELETE FROM rol_permisos WHERE modulo=? AND accion=?", (MODULO, ACCION))
    conn.commit()
    logger.info("274: %s concesiones de %s.%s retiradas.", max(cur.rowcount or 0, 0),
                MODULO, ACCION)


up = run
