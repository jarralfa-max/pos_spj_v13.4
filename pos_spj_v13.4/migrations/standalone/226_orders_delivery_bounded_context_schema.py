# migrations/standalone/226_orders_delivery_bounded_context_schema.py
"""Pedidos/Delivery bounded context — born-clean UUIDv7 schema (ORD-3).

Creates the new `customer_orders`/`customer_order_lines`/
`orders_delivery_outbox` tables for the domain entities built in ORD-2
(backend/domain/orders_delivery/entities.py). These are NEW tables, distinct
from and not a replacement for the legacy `delivery_orders`/`delivery_items`/
`delivery_order_history`/`pedidos_whatsapp`/`pedidos_whatsapp_items` tables
(`migrations/m000_base_schema.py`) — see
docs/refactor/orders_delivery_legacy_inventory.md for what still owns
production traffic today (`core/services/delivery_service.py` /
`core/delivery/`, backing the live `modulos/delivery.py` UI).
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema

logger = logging.getLogger("spj.migrations.226")


def run(conn) -> None:
    create_orders_delivery_schema(conn)
    conn.commit()
    logger.info("226: orders/delivery bounded context schema created (born-clean UUIDv7).")


up = run
