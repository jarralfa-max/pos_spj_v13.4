# migrations/standalone/189_customer_privacy_bounded_context_schema.py
"""Customer Privacy bounded context — born-clean UUIDv7 schema (CRM-9).

Creates the canonical consent/preference/privacy-request/retention-policy
tables from
``backend/infrastructure/db/schema/customer_privacy_schema.py`` (single
source of DDL). Independent of ``crm_schema.py``/
``customer_service_schema.py``/``customer_credit_schema.py`` — separate
sub-bounded-context, separate schema file, separate migration, same
convention as migrations 186/188.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customer_privacy_schema import (
    create_customer_privacy_schema,
)

logger = logging.getLogger("spj.migrations.189")


def run(conn) -> None:
    create_customer_privacy_schema(conn)
    conn.commit()
    logger.info("189: Customer Privacy (consentimientos/preferencias/solicitudes/retención) bounded context schema creado (born-clean UUIDv7).")


up = run
