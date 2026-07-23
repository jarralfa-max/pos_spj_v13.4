# migrations/standalone/136_products_bounded_context_schema.py
"""Products bounded context — born-clean UUIDv7 schema (PROD-4).

Creates the canonical products master + meat classification + audit/outbox tables
(``products``, ``species``, ``anatomical_regions``, ``cut_classifications``,
``product_authorization_log``, ``product_audit_log``, ``product_outbox``,
``product_processed_events``) by running the idempotent ``create_products_schema``.

These canonical English tables do NOT touch the legacy Spanish ``productos`` /
``recetas`` tables, which keep their live readers until PROD-17/PROD-19. DDL lives
solely in ``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.136")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("136: canonical products schema ensured (master + meat classification).")


up = run
