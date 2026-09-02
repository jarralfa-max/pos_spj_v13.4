# migrations/standalone/219_integrations_schema.py
"""SET-19 — Integrations schema (Definitions, Instances, Credentials,
Health, Webhooks).

Creates `integration_definitions`, `integration_instances`,
`integration_health_checks`, `webhook_endpoints`. Generalizes the two
real, live integrations already in this codebase (WhatsApp, MercadoPago
— both untouched by this migration) into a governance catalog; does not
migrate their actual configuration/secrets into these tables.

DDL lives in backend/infrastructure/db/schema/integrations_schema.py;
only this migration may call create_integrations_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.integrations_schema import create_integrations_schema

logger = logging.getLogger("spj.migrations.219")


def run(conn) -> None:
    create_integrations_schema(conn)
    conn.commit()
    logger.info(
        "219: integration_definitions/integration_instances/integration_health_checks/"
        "webhook_endpoints schema created."
    )


up = run
