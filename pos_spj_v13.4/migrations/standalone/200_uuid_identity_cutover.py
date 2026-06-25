"""Migración 200 — CORTE UUID GLOBAL DE IDENTIDAD (FASE 2.5).

⚠️  MIGRACIÓN DESTRUCTIVA Y GATED. NO está registrada en ``migrations/engine.py``
    a propósito: nunca debe ejecutarse automáticamente en el bootstrap. Convierte
    TODA PK/FK entera a UUIDv7 ``TEXT`` en una sola transacción atómica.

Precondiciones obligatorias (REGLA CERO, pasos 1-3):
  1. Aplicación cerrada, sin otras instancias.
  2. Backup completo del archivo .db verificado.
  3. ``CUTOVER_SPECS`` AUDITADO y COMPLETO (PK + cada FK funcional → tabla padre).
     El spec generado resuelve hoy las 256 tablas con 0 FK sin mapear.

Ejecución (manual, gated):
    SPJ_UUID_CUTOVER_CONFIRMED=1  +  conn explícita  ->  run(conn)

El motor (``backend/infrastructure/db/uuid_cutover.py``) construye mapas
``old_id -> uuid``, reescribe PK+FK, preserva índices/triggers/vistas, valida
conteos y corre ``PRAGMA foreign_key_check``; cualquier fallo revierte todo (no
se permite migración parcial). Probado de extremo a extremo sobre el esquema
real bootstrapeado: 256 tablas, foreign_key_check vacío, 0 PK enteras restantes.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.infrastructure.db.uuid_cutover import UuidCutover, UuidCutoverError

logger = logging.getLogger("spj.migrations")

# Spec auto-generado por la auditoría de esquema (256 tablas, 15 junction pk=None,
# 0 FK sin resolver). Regenerar con:
#   python tools/refactor_control/build_cutover_spec.py --db <schema.db>
from migrations.standalone._cutover_spec_generated import CUTOVER_SPECS  # noqa: E402

# True: el spec resuelve el 100% de PK/FK y el corte está probado end-to-end
# (PRAGMA foreign_key_check vacío, 0 PK enteras restantes) sobre el esquema real.
SPEC_IS_COMPLETE = True


def audit_integer_pks(conn: Any) -> dict[str, list[str]]:
    """Return {table: [cols]} for every remaining INTEGER PRIMARY KEY column.

    Post-cut debe estar vacío (REGLA CERO paso 13: bloquear si queda PK entera)."""
    violations: dict[str, list[str]] = {}
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall():
        if table.startswith("sqlite_") or table.startswith("schema_"):
            continue
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
            col_name, col_type, pk = row[1], (row[2] or ""), row[5]
            if pk and col_type.upper() in ("INTEGER", "INT"):
                violations.setdefault(table, []).append(col_name)
    return violations


def run(conn):
    if os.environ.get("SPJ_UUID_CUTOVER_CONFIRMED") != "1":
        raise RuntimeError(
            "Migración 200 (corte UUID) es destructiva y gated. "
            "Requiere SPJ_UUID_CUTOVER_CONFIRMED=1, backup verificado y app cerrada."
        )
    if not SPEC_IS_COMPLETE:
        raise RuntimeError(
            "CUTOVER_SPECS está incompleto. Audita las tablas (PK+FK) y pon "
            "SPEC_IS_COMPLETE=True antes de ejecutar el corte."
        )
    logger.warning("[CUTOVER] iniciando corte UUID global sobre %d tablas", len(CUTOVER_SPECS))
    counts = UuidCutover(conn, CUTOVER_SPECS).run()
    # Paso 13: bloquear si quedó cualquier identidad entera tras el corte.
    remaining = audit_integer_pks(conn)
    if remaining:
        raise UuidCutoverError(
            f"corte incompleto: aún hay PK enteras tras el corte: {remaining}"
        )
    logger.warning("[CUTOVER] completado. Filas migradas: %s", counts)
    return counts
