# migrations/standalone/220_notifications_schema.py
"""SET-20 — Notifications schema (Accounts, Templates, Channels,
Routing).

Creates `notification_accounts`, `notification_templates`,
`notification_routes` — generalizing the real, live WhatsApp template
catalog (`whatsapp_service/messaging/templates.py::TEMPLATES`) and the
real, live channel senders
(`backend/infrastructure/integrations/cash_notification_senders.py`,
`loss_notification_senders.py`) into a governance catalog. Neither is
migrated or touched by this migration.

Depends on migration 219 (Integrations) only loosely —
`notification_accounts.integration_instance_id` is an opaque UUID
reference, not a real FK.

DDL lives in backend/infrastructure/db/schema/notifications_schema.py;
only this migration may call create_notifications_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.notifications_schema import create_notifications_schema

logger = logging.getLogger("spj.migrations.220")


def run(conn) -> None:
    create_notifications_schema(conn)
    conn.commit()
    logger.info("220: notification_accounts/notification_templates/notification_routes schema created.")


up = run
