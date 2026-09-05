# migrations/standalone/252_meat_processing_resources_schema.py
"""Meat Processing (Procesamiento Cárnico) — Recursos y capacidad schema (PROC-19).

Adds production_areas/work_centers/production_stations/production_equipment/
equipment_assignments (§19/§33) on top of the núcleo productivo schema (187)
and every prior meat-processing migration, none of which is touched here. DDL
lives in ``backend/infrastructure/db/schema/meat_processing_schema.py``
(``create_meat_processing_resources_schema``).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.meat_processing_schema import (
    create_meat_processing_resources_schema,
)

logger = logging.getLogger("spj.migrations.252")


def run(conn) -> None:
    create_meat_processing_resources_schema(conn)
    conn.commit()
    logger.info(
        "252: meat processing resources schema created (production_areas, "
        "work_centers, production_stations, production_equipment, "
        "equipment_assignments).")


up = run
