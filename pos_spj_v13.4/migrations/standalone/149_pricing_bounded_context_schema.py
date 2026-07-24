# migrations/standalone/149_pricing_bounded_context_schema.py
"""Pricing/costing bounded context — born-clean UUIDv7 schema (PRC-3).

Creates the canonical pricing tables (price_list, product_price, volume_price,
customer_price_list, product_cost, price_change_log, pricing_authorization_log,
pricing_outbox) by running the idempotent create_pricing_schema. Money amounts are
TEXT Decimal (no REAL). These canonical English tables do NOT touch the legacy
Spanish listas_precio/precios_lista/precios_volumen/historial_precios, which keep
their live readers until PRC-6/PRC-8. DDL lives solely in pricing_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema

logger = logging.getLogger("spj.migrations.149")


def run(conn) -> None:
    create_pricing_schema(conn)
    conn.commit()
    logger.info("149: canonical pricing/costing schema ensured.")


up = run
