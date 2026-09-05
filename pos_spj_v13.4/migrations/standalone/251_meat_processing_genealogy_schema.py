# migrations/standalone/251_meat_processing_genealogy_schema.py
"""Meat Processing (Procesamiento Cárnico) — Trazabilidad schema (PROC-18).

Adds process_genealogy_links (§38) on top of the núcleo productivo schema
(187) and every prior meat-processing migration, none of which is touched
here. DDL lives in
``backend/infrastructure/db/schema/meat_processing_schema.py``
(``create_meat_processing_genealogy_schema``).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.meat_processing_schema import (
    create_meat_processing_genealogy_schema,
)

logger = logging.getLogger("spj.migrations.251")


def run(conn) -> None:
    create_meat_processing_genealogy_schema(conn)
    conn.commit()
    logger.info("251: meat processing genealogy schema created (process_genealogy_links).")


up = run
