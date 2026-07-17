# migrations/standalone/119_supplier_bounded_context_schema.py
"""Suppliers bounded context — born-clean UUIDv7 schema.

Creates the canonical supplier master and its satellite tables from
``backend/infrastructure/db/schema/supplier_schema.py`` (single source of DDL).

The legacy minimal tables ``proveedores`` / ``suppliers`` still have live
purchase/finance readers and are NOT dropped here — their readers migrate to the
canonical master in SUP-6, after which they can be removed.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema

logger = logging.getLogger("spj.migrations.119")


def run(conn) -> None:
    create_supplier_schema(conn)
    conn.commit()
    logger.info("119: supplier bounded context schema created (born-clean UUIDv7).")


up = run
