# migrations/standalone/221_feature_flags_schema.py
"""SET-21 — Feature Flags schema (Flags, Rules, Rollout, Approval).

Creates `ff_flags`, `ff_rules`, `ff_change_requests` — a born-clean,
UUIDv7-native replacement concept for the legacy dual-schema
`feature_flags` table
(`repositories/feature_flag_repository.py` detects `feature_name/enabled/
branch_id` vs legacy `clave/activo` columns at runtime via `PRAGMA
table_info`, see SET-0's audit §6.3). Uses `ff_` table names precisely to
avoid colliding with that legacy table, which keeps serving
`modulos/config_modules.py`/`modulos/delivery.py` unchanged.

DDL lives in backend/infrastructure/db/schema/feature_flags_schema.py;
only this migration may call create_feature_flags_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.feature_flags_schema import create_feature_flags_schema

logger = logging.getLogger("spj.migrations.221")


def run(conn) -> None:
    create_feature_flags_schema(conn)
    conn.commit()
    logger.info("221: ff_flags/ff_rules/ff_change_requests schema created.")


up = run
