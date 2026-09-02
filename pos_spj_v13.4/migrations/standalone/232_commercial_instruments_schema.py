# migrations/standalone/232_commercial_instruments_schema.py
"""Commercial Instruments bounded context — born-clean UUIDv7 schema
(LOY-12, §21-22): coupon definitions, instances, redemptions.

Separate bounded context from Fidelidad/Loyalty (master prompt §7.2) —
coupons are commercial instruments in their own right, not owned by the
points/tiers/rewards domain, even though they share the same GROWTH_ENGINE
permission surface.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.commercial_instruments_schema import (
    create_commercial_instruments_schema,
)

logger = logging.getLogger("spj.migrations.232")


def run(conn) -> None:
    create_commercial_instruments_schema(conn)
    conn.commit()
    logger.info("232: commercial instruments schema created (coupons, born-clean UUIDv7).")


up = run
