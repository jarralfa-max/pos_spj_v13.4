# migrations/standalone/118_hr_bounded_context_schema.py
"""HR bounded context — born-clean UUIDv7 schema cutover.

Development-phase rule: no data rescue, no dual routes. Drops legacy HR trace
tables (asistencias, nomina_records, evaluaciones_personal, turno_*) and creates
the canonical HR schema from ``backend/infrastructure/db/schema/hr_schema.py``.

The DDL lives in the schema module (single source of truth); this migration is
the only execution entry point.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.hr_schema import (
    create_hr_schema,
    drop_legacy_hr_tables,
)

logger = logging.getLogger("spj.migrations.118")


def run(conn) -> None:
    dropped = drop_legacy_hr_tables(conn)
    if dropped:
        logger.info("118: dropped %d legacy HR tables: %s", len(dropped), ", ".join(dropped))
    create_hr_schema(conn)
    conn.commit()
    logger.info("118: HR bounded context schema created (born-clean UUIDv7).")


up = run
