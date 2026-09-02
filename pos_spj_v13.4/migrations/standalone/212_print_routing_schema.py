# migrations/standalone/212_print_routing_schema.py
"""SET-8 — Print Routing schema (Impresoras: perfiles, routing, failover).

Creates `print_routes` (§25 — document_type → primary printer + ordered
fallback chain, scoped by branch/workstation/module/channel) and
`printer_test_results` (§21/§23 — append-only log of on-demand test
prints).

DDL lives in backend/infrastructure/db/schema/device_management_schema.py;
only this migration may call create_print_routing_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.device_management_schema import create_print_routing_schema

logger = logging.getLogger("spj.migrations.212")


def run(conn) -> None:
    create_print_routing_schema(conn)
    conn.commit()
    logger.info("212: print_routes + printer_test_results schema created.")


up = run
