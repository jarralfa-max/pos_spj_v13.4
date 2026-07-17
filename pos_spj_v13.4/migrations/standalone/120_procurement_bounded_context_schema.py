# migrations/standalone/120_procurement_bounded_context_schema.py
"""Procurement bounded context — born-clean UUIDv7 schema.

Creates the canonical procurement tables (direct purchases, requisitions,
RFQ/quotes, purchase orders with versioning, goods receipts, supplier invoices,
authorization log, audit, outbox, processed-events) from
``backend/infrastructure/db/schema/procurement_schema.py`` (single source of DDL).

The legacy Spanish tables (compras / ordenes_compra / recepciones /
purchase_requests) still have live readers and are NOT touched here — their
readers migrate to the canonical procurement context in PUR-11.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.120")


def run(conn) -> None:
    create_procurement_schema(conn)
    conn.commit()
    logger.info("120: procurement bounded context schema created (born-clean UUIDv7).")


up = run
