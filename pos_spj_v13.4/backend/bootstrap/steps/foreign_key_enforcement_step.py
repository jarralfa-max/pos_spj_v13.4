"""ForeignKeyEnforcementStep — Slice 0 de la arquitectura híbrida (ADR-006, R-02).

La conexión del escritorio (`DatabaseIntegrityStep`) se abría sin
`PRAGMA foreign_keys`: SQLite las deja APAGADAS por omisión. Sólo las
migraciones 016/026 las encendían, y sólo el día que corrían; en cada arranque
posterior la base aceptaba huérfanos que PostgreSQL rechazará al consolidar.

Se encienden aquí, DESPUÉS de migrar, nunca antes: varias migraciones
históricas reconstruyen tablas (crear nueva → copiar → `DROP` → renombrar) y
con las llaves activas ese `DROP` borraría en cascada o fallaría.

Antes de encenderlas se mide `PRAGMA foreign_key_check`. Con violaciones NO se
encienden —el POS debe abrir igual (continuidad de ventas)— y el arranque lo
reporta como advertencia con las tablas afectadas, para corregirlas sin perder
datos. Medido sobre la copia de la base real el 2026-10-23: 0 violaciones.
"""
from __future__ import annotations

import logging

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult

logger = logging.getLogger("spj.bootstrap.foreign_keys")


def enable_foreign_keys(conn) -> list[tuple[str, int]]:
    """Enciende las llaves foráneas si la base las cumple. Devuelve las
    violaciones por tabla (vacío = encendidas)."""
    if conn.in_transaction:
        conn.commit()   # el PRAGMA no tiene efecto dentro de una transacción
    conteo: dict[str, int] = {}
    for fila in conn.execute("PRAGMA foreign_key_check").fetchall():
        conteo[str(fila[0])] = conteo.get(str(fila[0]), 0) + 1
    if conteo:
        return sorted(conteo.items())
    conn.execute("PRAGMA foreign_keys=ON")
    return []


class ForeignKeyEnforcementStep:
    name = "foreign_key_enforcement"
    resulting_state = BootstrapState.SCHEMA_VALIDATED

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        if context.conn is None:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.BOOTSTRAP_INVALID,
                "foreign_key_enforcement ejecutado sin una conexión abierta.")
        violaciones = enable_foreign_keys(context.conn)
        if violaciones:
            detalle = ", ".join(f"{tabla} ({n})" for tabla, n in violaciones)
            logger.warning("Llaves foráneas NO activadas; violaciones: %s", detalle)
            return BootstrapStepResult.warning(
                self.name, BootstrapFailureReason.FOREIGN_KEYS_NOT_ENFORCED,
                f"Hay registros que apuntan a otros inexistentes ({detalle}); las llaves "
                "foráneas siguen apagadas hasta corregirlos.")
        return BootstrapStepResult.ok(self.name, "Llaves foráneas activas.")
