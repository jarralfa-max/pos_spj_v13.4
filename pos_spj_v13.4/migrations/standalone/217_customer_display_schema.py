# migrations/standalone/217_customer_display_schema.py
"""SET-17 — Customer Display schema (Displays, Layouts, Modes, Gateway).

Creates `customer_displays` and `display_layouts` (§"Modes"/"Layouts").
`CustomerDisplayGatewayPort` is a pure domain Protocol with no schema of
its own — see `backend/domain/customer_display/gateway_ports.py`'s
docstring for why no real implementation exists yet.

Depends on migration 210 (workstations) — `customer_displays.workstation_id`
references that table.

DDL lives in backend/infrastructure/db/schema/customer_display_schema.py;
only this migration may call create_customer_display_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customer_display_schema import create_customer_display_schema

logger = logging.getLogger("spj.migrations.217")


def run(conn) -> None:
    create_customer_display_schema(conn)
    conn.commit()
    logger.info("217: customer_displays/display_layouts schema created.")


up = run
