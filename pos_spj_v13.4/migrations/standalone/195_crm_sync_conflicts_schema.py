# migrations/standalone/195_crm_sync_conflicts_schema.py
"""CRM-20 — Offline-first sync conflicts (§91-92).

Adds `customer_sync_conflicts` (Customer Master) and `crm_sync_conflicts`
(CRM) — never lets an incoming remote mutation silently overwrite a
locally-changed row; detection uses optimistic concurrency on the existing
`customers.version` counter / `updated_at` timestamps, no new column needed
on the entity tables themselves.

Only calls the two existing schema functions — idempotent, additive.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.crm_schema import create_crm_schema
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema

logger = logging.getLogger("spj.migrations.195")


def run(conn) -> None:
    create_customers_crm_schema(conn)
    create_crm_schema(conn)
    conn.commit()
    logger.info("195: customer_sync_conflicts/crm_sync_conflicts creadas (CRM-20).")


up = run
