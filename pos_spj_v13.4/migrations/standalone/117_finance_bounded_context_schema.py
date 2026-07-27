# migrations/standalone/117_finance_bounded_context_schema.py
"""Finance bounded context — born-clean UUIDv7 schema cutover.

Development-phase rule (SPJ_REFACTOR_SKILL.md): no data rescue, no dual routes.
This migration DROPS every legacy finance table from previous generations
(m000/035/052/059/061/066/082/083/084) and creates the canonical double-entry
schema defined in ``backend/infrastructure/db/schema/finance_schema.py``.

The DDL itself lives in the schema module (single source of truth); this
migration is the only execution entry point, honoring the rule that schema
changes happen exclusively inside ``migrations/``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.finance_schema import (
    create_finance_schema,
    drop_legacy_finance_tables,
)

logger = logging.getLogger("spj.migrations.117")


def run(conn) -> None:
    dropped = drop_legacy_finance_tables(conn)
    if dropped:
        logger.info("117: dropped %d legacy finance tables: %s", len(dropped), ", ".join(dropped))
    create_finance_schema(conn)
    conn.commit()
    logger.info("117: finance bounded context schema created (born-clean UUIDv7).")
