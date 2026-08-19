# migrations/standalone/198_sales_bounded_context_schema.py
"""Sales/POS bounded context — born-clean UUIDv7 schema (SALES-4/POS-4).

Creates the new `sales`/`sale_lines`/`sales_outbox` tables for the
`Sale`/`SaleLine` domain aggregate built in SALES-3
(backend/domain/sales/entities.py). These are NEW tables, distinct from and
not a replacement for the legacy `ventas`/`detalles_venta` tables — see
backend/infrastructure/db/schema/sales_schema.py's own docstring for the
naming rationale and what still owns production traffic today.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.sales_schema import create_sales_schema

logger = logging.getLogger("spj.migrations.198")


def run(conn) -> None:
    create_sales_schema(conn)
    conn.commit()
    logger.info("198: sales bounded context schema created (born-clean UUIDv7).")


up = run
