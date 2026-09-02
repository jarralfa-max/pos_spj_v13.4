# migrations/standalone/235_sweepstakes_bounded_context_schema.py
"""Sweepstakes/Sorteos bounded context — born-clean UUIDv7 schema (LOY-15,
§27-28): campaigns, rules, prizes, entries, tickets, draws, winners.

Separate bounded context from Fidelidad/Loyalty and from the legacy
`raffle_*` tables (migration 113) — a sweepstakes/rifa is its own
promotional mechanism, sharing only the GROWTH_ENGINE permission surface.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.sweepstakes_schema import create_sweepstakes_schema

logger = logging.getLogger("spj.migrations.235")


def run(conn) -> None:
    create_sweepstakes_schema(conn)
    conn.commit()
    logger.info("235: sweepstakes bounded context schema created (born-clean UUIDv7).")


up = run
