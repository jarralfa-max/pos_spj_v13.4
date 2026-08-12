# migrations/standalone/186_customer_service_bounded_context_schema.py
"""Customer Service (atención al cliente) bounded context — born-clean
UUIDv7 schema (CRM-7).

Creates the canonical service_cases/SLA tables from
``backend/infrastructure/db/schema/customer_service_schema.py`` (single
source of DDL). Independent of ``crm_schema.py`` (migrations 182/183/185)
— separate sub-bounded-context, separate schema file, separate migration,
same convention as migration 181 (``customers``) vs. 182 (``crm``).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customer_service_schema import (
    create_customer_service_schema,
)

logger = logging.getLogger("spj.migrations.186")


def run(conn) -> None:
    create_customer_service_schema(conn)
    conn.commit()
    logger.info("186: Customer Service (casos/SLA) bounded context schema creado (born-clean UUIDv7).")


up = run
