# migrations/standalone/181_customers_crm_bounded_context_schema.py
"""Customer Master bounded context — born-clean UUIDv7 schema (CRM-3).

Creates the canonical customer master and its satellite tables from
``backend/infrastructure/db/schema/customers_crm_schema.py`` (single source
of DDL).

The legacy ``clientes`` table (docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md
§4) still has live readers throughout Ventas/Fidelidad/WhatsApp/Finanzas and
is NOT touched here — its readers migrate to the canonical customers table in
CRM-21/22, after which it can be removed.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customers_crm_schema import (
    create_customers_crm_schema,
)

logger = logging.getLogger("spj.migrations.181")


def run(conn) -> None:
    create_customers_crm_schema(conn)
    conn.commit()
    logger.info("181: customers/CRM bounded context schema created (born-clean UUIDv7).")


up = run
