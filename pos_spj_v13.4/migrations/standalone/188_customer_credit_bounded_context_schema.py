# migrations/standalone/188_customer_credit_bounded_context_schema.py
"""Customer Credit bounded context — born-clean UUIDv7 schema (CRM-8).

Creates the canonical credit profile tables from
``backend/infrastructure/db/schema/customer_credit_schema.py`` (single
source of DDL). Independent of ``crm_schema.py``/
``customer_service_schema.py`` — separate sub-bounded-context, separate
schema file, separate migration, same convention as migration 186
(``customer_service``).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customer_credit_schema import (
    create_customer_credit_schema,
)

logger = logging.getLogger("spj.migrations.188")


def run(conn) -> None:
    create_customer_credit_schema(conn)
    conn.commit()
    logger.info("188: Customer Credit (perfil/límites) bounded context schema creado (born-clean UUIDv7).")


up = run
