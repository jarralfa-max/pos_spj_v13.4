# migrations/standalone/187_meat_processing_bounded_context_schema.py
"""Meat Processing (Procesamiento Cárnico) bounded context — born-clean UUIDv7
schema (PROC-3).

Creates the canonical núcleo productivo tables from
``backend/infrastructure/db/schema/meat_processing_schema.py`` (single source
of DDL): processing_orders, processing_batches, process_executions,
material_consumptions, process_outputs, process_weighings,
yield_reconciliations, plus authorization/audit/outbox/processed-events support
tables.

The legacy production tables (``producciones``, ``produccion_detalle``, see
``docs/refactor/PROC-0_legacy_audit.md``) are NOT touched here — they keep their
live readers (`modulos/produccion.py`, `core/production/production_engine.py`)
until the relocation completes and PROC-25 removes them.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.meat_processing_schema import (
    create_meat_processing_schema,
)

logger = logging.getLogger("spj.migrations.187")


def run(conn) -> None:
    create_meat_processing_schema(conn)
    conn.commit()
    logger.info("187: meat processing bounded context schema created (born-clean UUIDv7).")


up = run
