# migrations/standalone/211_device_management_schema.py
"""SET-7 — Device Management schema.

Creates `device_profiles`, `devices`, `workstation_device_assignments`.
Deliberately does NOT touch or migrate `hardware_config` (legacy,
single-row-per-type, no branch/workstation scoping) — that table's live
consumers (`core/services/hardware_service.py`, `modulos/config_hardware.py`,
`hardware/*.py`) are cut over to this new model in the printer/scale/
cash-drawer SETs (SET-8/9/10), not here. This migration only depends on
`sucursales` (m000) and `workstations` (migration 210) already existing.

DDL lives in backend/infrastructure/db/schema/device_management_schema.py;
only this migration may call create_device_management_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.device_management_schema import create_device_management_schema

logger = logging.getLogger("spj.migrations.211")


def run(conn) -> None:
    create_device_management_schema(conn)
    conn.commit()
    logger.info("211: device_profiles + devices + workstation_device_assignments schema created.")


up = run
