# migrations/standalone/249_meat_processing_packaging_schema.py
"""Meat Processing (Procesamiento Cárnico) — Empaque schema (PROC-13).

Adds packaging_executions and production_labels (§25) on top of the núcleo
productivo schema (migration 187) and the preparación/ejecución schema
(migration 248), neither of which is touched here. DDL lives in
``backend/infrastructure/db/schema/meat_processing_schema.py``
(``create_meat_processing_packaging_schema``).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.meat_processing_schema import (
    create_meat_processing_packaging_schema,
)

logger = logging.getLogger("spj.migrations.249")


def run(conn) -> None:
    create_meat_processing_packaging_schema(conn)
    conn.commit()
    logger.info("249: meat processing packaging schema created "
                "(packaging_executions, production_labels).")


up = run
