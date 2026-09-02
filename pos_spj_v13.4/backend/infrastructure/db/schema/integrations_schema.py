"""Integrations schema — SET-19.

DDL lives only here; only migration 219 may call
`create_integrations_schema`. Backs `backend/domain/integrations/`
(SET-19): `integration_definitions` mirrors `IntegrationDefinition`,
`integration_instances` mirrors `IntegrationInstance`,
`integration_health_checks` mirrors `IntegrationHealthCheck`,
`webhook_endpoints` mirrors `WebhookEndpoint`.

No FK to any other bounded context's schema — Integrations is a
standalone catalog, unlike Device Management/Document Output/Customer
Display, which all depend on Settings' `workstations` table.
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_INTEGRATION_CATEGORIES = "'MESSAGING','PAYMENTS','FISCAL','LOCATION','EMAIL','SMS','OTHER'"
_WEBHOOK_SIGNATURE_SCHEMES = "'HMAC_SHA256_HEADER','MERCADOPAGO_TS_V1','NONE'"

_INTEGRATION_DEFINITIONS_DDL = f"""
    CREATE TABLE IF NOT EXISTS integration_definitions (
        id                            TEXT PRIMARY KEY CHECK({_uuid('id')}),
        code                          TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        name                          TEXT NOT NULL CHECK(trim(name)<>''),
        category                      TEXT NOT NULL CHECK(category IN ({_INTEGRATION_CATEGORIES})),
        required_credential_names_json TEXT NOT NULL DEFAULT '[]',
        active                        INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at                    TEXT NOT NULL,
        updated_at                    TEXT NOT NULL
    )
"""

_INTEGRATION_INSTANCES_DDL = f"""
    CREATE TABLE IF NOT EXISTS integration_instances (
        id                        TEXT PRIMARY KEY CHECK({_uuid('id')}),
        definition_id             TEXT NOT NULL REFERENCES integration_definitions(id) CHECK({_uuid('definition_id')}),
        name                      TEXT NOT NULL CHECK(trim(name)<>''),
        config_json               TEXT NOT NULL DEFAULT '{{}}',
        credential_references_json TEXT NOT NULL DEFAULT '{{}}',
        active                    INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at                TEXT NOT NULL,
        updated_at                TEXT NOT NULL
    )
"""

_INTEGRATION_HEALTH_CHECKS_DDL = f"""
    CREATE TABLE IF NOT EXISTS integration_health_checks (
        id            TEXT PRIMARY KEY CHECK({_uuid('id')}),
        instance_id   TEXT NOT NULL REFERENCES integration_instances(id) CHECK({_uuid('instance_id')}),
        success       INTEGER NOT NULL CHECK(success IN (0,1)),
        message       TEXT NOT NULL DEFAULT '',
        checked_at    TEXT NOT NULL
    )
"""

_WEBHOOK_ENDPOINTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS webhook_endpoints (
        id                        TEXT PRIMARY KEY CHECK({_uuid('id')}),
        instance_id               TEXT NOT NULL REFERENCES integration_instances(id) CHECK({_uuid('instance_id')}),
        code                      TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        path                      TEXT NOT NULL CHECK(trim(path)<>''),
        signature_scheme          TEXT NOT NULL DEFAULT 'NONE' CHECK(signature_scheme IN ({_WEBHOOK_SIGNATURE_SCHEMES})),
        signing_secret_reference  TEXT,
        active                    INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        last_received_at          TEXT,
        created_at                TEXT NOT NULL,
        updated_at                TEXT NOT NULL
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_integration_definitions_active ON integration_definitions(active)",
    "CREATE INDEX IF NOT EXISTS idx_integration_instances_definition ON integration_instances(definition_id)",
    "CREATE INDEX IF NOT EXISTS idx_integration_instances_active ON integration_instances(active)",
    "CREATE INDEX IF NOT EXISTS idx_integration_health_checks_instance ON integration_health_checks(instance_id)",
    "CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_instance ON webhook_endpoints(instance_id)",
)


def create_integrations_schema(conn) -> None:
    conn.execute(_INTEGRATION_DEFINITIONS_DDL)
    conn.execute(_INTEGRATION_INSTANCES_DDL)
    conn.execute(_INTEGRATION_HEALTH_CHECKS_DDL)
    conn.execute(_WEBHOOK_ENDPOINTS_DDL)
    for statement in _INDEXES:
        conn.execute(statement)
