"""Migración 200 — CORTE UUID GLOBAL DE IDENTIDAD (FASE 2.5).

⚠️  MIGRACIÓN DESTRUCTIVA Y GATED. NO está registrada en ``migrations/engine.py``
    a propósito: nunca debe ejecutarse automáticamente en el bootstrap. Convierte
    TODA PK/FK entera a UUIDv7 ``TEXT`` en una sola transacción atómica.

Precondiciones obligatorias (REGLA CERO, pasos 1-3):
  1. Aplicación cerrada, sin otras instancias.
  2. Backup completo del archivo .db verificado.
  3. ``CUTOVER_SPECS`` AUDITADO y COMPLETO para las 191 tablas (PK + cada FK
     funcional → tabla padre). El spec de abajo es un PUNTO DE PARTIDA de las
     entidades núcleo; está INCOMPLETO y debe completarse/validarse antes de correr.

Ejecución (manual, gated):
    SPJ_UUID_CUTOVER_CONFIRMED=1  +  conn explícita  ->  run(conn)

El motor (``backend/infrastructure/db/uuid_cutover.py``) construye mapas
``old_id -> uuid``, reescribe PK+FK, valida conteos y corre ``PRAGMA
foreign_key_check``; cualquier fallo revierte todo (no se permite migración parcial).
"""

from __future__ import annotations

import logging
import os

from backend.infrastructure.db.uuid_cutover import UuidCutover

logger = logging.getLogger("spj.migrations")

# Spec auto-generado por la auditoría de esquema (256 tablas, 15 junction pk=None).
# Generado con: python tools/refactor_control/build_cutover_spec.py --db <schema.db>
from migrations.standalone._cutover_spec_generated import CUTOVER_SPECS  # noqa: E402

# El generado resuelve por convención casi todo, pero deja ~24 columnas FK
# context-dependent / polimórficas SIN mapear (ver comentarios al final del módulo
# generado). Deben resolverse con overrides por-tabla y validarse contra datos
# reales antes de habilitar el corte.
SPEC_IS_COMPLETE = False  # True solo tras resolver las FK context-dependent + pre-auditar huérfanas.


def run(conn):
    if os.environ.get("SPJ_UUID_CUTOVER_CONFIRMED") != "1":
        raise RuntimeError(
            "Migración 200 (corte UUID) es destructiva y gated. "
            "Requiere SPJ_UUID_CUTOVER_CONFIRMED=1, backup verificado y app cerrada."
        )
    if not SPEC_IS_COMPLETE:
        raise RuntimeError(
            "CUTOVER_SPECS está incompleto. Audita las 191 tablas (PK+FK) y pon "
            "SPEC_IS_COMPLETE=True antes de ejecutar el corte."
        )
    logger.warning("[CUTOVER] iniciando corte UUID global sobre %d tablas", len(CUTOVER_SPECS))
    counts = UuidCutover(conn, CUTOVER_SPECS).run()
    logger.warning("[CUTOVER] completado. Filas migradas: %s", counts)
    return counts
