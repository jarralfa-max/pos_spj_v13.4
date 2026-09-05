# migrations/standalone/250_meat_processing_rework_schema.py
"""Meat Processing (Procesamiento Cárnico) — Reprocesos schema (PROC-17).

Adds rework_orders (§29) on top of the núcleo productivo schema (187) and the
preparación/ejecución/empaque schemas (248/249), none of which is touched
here. DDL lives in
``backend/infrastructure/db/schema/meat_processing_schema.py``
(``create_meat_processing_rework_schema``).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.meat_processing_schema import (
    create_meat_processing_rework_schema,
)

logger = logging.getLogger("spj.migrations.250")


def run(conn) -> None:
    create_meat_processing_rework_schema(conn)
    conn.commit()
    logger.info("250: meat processing rework schema created (rework_orders).")


up = run
