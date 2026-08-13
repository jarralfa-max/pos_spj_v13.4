# migrations/standalone/190_crm_segmentation_bounded_context_schema.py
"""CRM (relationship) bounded context — Propietario/Territorios/Carteras/
Segmentación/Etiquetas (CRM-10).

Creates `sales_territories`/`customer_portfolios`/`customer_ownerships`/
`portfolio_assignments`/`customer_segments`/`customer_segment_memberships`/
`customer_tags`/`customer_tag_assignments` from
``backend/infrastructure/db/schema/crm_schema.py`` (single source of DDL —
same file migrations 182/183/185 used for Leads/Opportunities/Activities).
No ALTER TABLE needed: these are brand-new tables, not new columns on an
existing one, so plain ``CREATE TABLE IF NOT EXISTS`` is idempotent on a
database that already ran 182/183/185.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.crm_schema import create_crm_schema

logger = logging.getLogger("spj.migrations.190")


def run(conn) -> None:
    create_crm_schema(conn)
    conn.commit()
    logger.info("190: CRM (propietario/territorios/carteras/segmentos/etiquetas) bounded context schema creado.")


up = run
