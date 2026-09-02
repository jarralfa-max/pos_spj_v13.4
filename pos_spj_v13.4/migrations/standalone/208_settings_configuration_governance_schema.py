# migrations/standalone/208_settings_configuration_governance_schema.py
"""SET-3 — Configuration Governance schema.

Creates `configuration_definitions` and `configuration_values`, backing
the SET-2 domain layer (`backend/domain/settings/`). Born-clean UUIDv7,
no legacy table reused or bridged — this is a new bounded context, not a
migration of `configuraciones`/`hardware_config` (those get cut over in a
later SET once device_management/document_output exist to absorb them).

DDL lives in backend/infrastructure/db/schema/settings_schema.py; only
this migration may call it.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.settings_schema import create_settings_schema

logger = logging.getLogger("spj.migrations.208")


def run(conn) -> None:
    create_settings_schema(conn)
    conn.commit()
    logger.info("208: configuration_definitions + configuration_values schema created.")


up = run
