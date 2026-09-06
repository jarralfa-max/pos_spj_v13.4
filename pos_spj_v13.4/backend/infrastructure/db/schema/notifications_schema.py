"""Notifications schema — SET-20.

DDL lives only here; only migration 220 may call
`create_notifications_schema`. Backs `backend/domain/notifications/`
(SET-20): `notification_accounts` mirrors `NotificationAccount`,
`notification_templates` mirrors `NotificationTemplate`,
`notification_routes` mirrors `NotificationRoute`.

`notification_routes.template_id`/`account_id` FK into this same
schema's own tables. No FK into Integrations' schema (SET-19) —
`notification_accounts.integration_instance_id` is an opaque UUID
reference, validated as UUIDv7 shape only, never a real FK, the same
"opaque reference, not a real dependency" discipline `print_jobs.
source_document_id` (Document Output, SET-11) already established.
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_NOTIFICATION_CHANNELS = "'WHATSAPP','SMS','EMAIL','PUSH'"

_NOTIFICATION_ACCOUNTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS notification_accounts (
        id                      TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        channel                 TEXT NOT NULL CHECK(channel IN ({_NOTIFICATION_CHANNELS})),
        name                    TEXT NOT NULL CHECK(trim(name)<>''),
        credential_reference    TEXT,
        integration_instance_id TEXT CHECK(integration_instance_id IS NULL OR ({_uuid('integration_instance_id')})),
        active                  INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at              TEXT NOT NULL,
        updated_at              TEXT NOT NULL
    )
"""

_NOTIFICATION_TEMPLATES_DDL = f"""
    CREATE TABLE IF NOT EXISTS notification_templates (
        id                    TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        code                  TEXT NOT NULL CHECK(trim(code)<>''),
        channel               TEXT NOT NULL CHECK(channel IN ({_NOTIFICATION_CHANNELS})),
        language              TEXT NOT NULL CHECK(trim(language)<>''),
        parameter_names_json  TEXT NOT NULL DEFAULT '[]',
        active                INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at            TEXT NOT NULL,
        updated_at            TEXT NOT NULL,
        UNIQUE(code, channel)
    )
"""

_NOTIFICATION_ROUTES_DDL = f"""
    CREATE TABLE IF NOT EXISTS notification_routes (
        id            TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        event_code    TEXT NOT NULL CHECK(trim(event_code)<>''),
        channel       TEXT NOT NULL CHECK(channel IN ({_NOTIFICATION_CHANNELS})),
        template_id   TEXT NOT NULL REFERENCES notification_templates(id) CHECK({_uuid('template_id')}),
        account_id    TEXT NOT NULL REFERENCES notification_accounts(id) CHECK({_uuid('account_id')}),
        active        INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_notification_accounts_channel ON notification_accounts(channel)",
    "CREATE INDEX IF NOT EXISTS idx_notification_accounts_active ON notification_accounts(active)",
    "CREATE INDEX IF NOT EXISTS idx_notification_templates_channel ON notification_templates(channel)",
    "CREATE INDEX IF NOT EXISTS idx_notification_routes_event_code ON notification_routes(event_code)",
    # §"Routing": at most one ACTIVE route per event_code — the
    # constraint that actually prevents "two active routes at once" for
    # the same event, same partial-unique-index discipline as
    # `ux_dtv_template_active` (document_output, SET-11).
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_routes_event_active "
    "ON notification_routes(event_code) WHERE active=1",
)


def create_notifications_schema(conn) -> None:
    conn.execute(_NOTIFICATION_ACCOUNTS_DDL)
    conn.execute(_NOTIFICATION_TEMPLATES_DDL)
    conn.execute(_NOTIFICATION_ROUTES_DDL)
    for statement in _INDEXES:
        conn.execute(statement)
