# migrations/standalone/248_meat_processing_preparation_execution_schema.py
"""Meat Processing (Procesamiento Cárnico) — Preparación/Ejecución schema
(PROC-7/PROC-8).

Adds material_requirements (§16), operator_assignments (§32),
process_step_executions (§20) and process_incidents (§30) on top of the
núcleo productivo schema created by migration 187. DDL lives in
``backend/infrastructure/db/schema/meat_processing_schema.py``
(``create_meat_processing_preparation_execution_schema``) — migration 187
itself is untouched, per the append-only migration convention.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.meat_processing_schema import (
    create_meat_processing_preparation_execution_schema,
)

logger = logging.getLogger("spj.migrations.248")


def run(conn) -> None:
    create_meat_processing_preparation_execution_schema(conn)
    conn.commit()
    logger.info("248: meat processing preparation/execution schema created "
                "(material_requirements, operator_assignments, "
                "process_step_executions, process_incidents).")


up = run
