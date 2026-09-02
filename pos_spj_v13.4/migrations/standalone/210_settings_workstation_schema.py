# migrations/standalone/210_settings_workstation_schema.py
"""SET-6 — Workstation schema.

Creates `workstations` (registro/estado/versión/offline — §17). FK to
the existing `sucursales(id)` — a workstation always belongs to a
concrete, already-existing branch, same pattern as `branch_profiles` in
migration 209.

DDL lives in backend/infrastructure/db/schema/settings_schema.py; only
this migration may call create_workstation_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.settings_schema import create_workstation_schema

logger = logging.getLogger("spj.migrations.210")


def run(conn) -> None:
    create_workstation_schema(conn)
    conn.commit()
    logger.info("210: workstations schema created.")


up = run
