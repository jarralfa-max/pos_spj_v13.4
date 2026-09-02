"""Configuración security schema — SET-1.

DDL lives only here; only migration 224 may call
`create_configuracion_security_schema`. Backs SET-1's "Auditoría en
caliente" requirement (§60): `configuracion_authorization_log` persists
`AuthorizationGrant` records (hot authorizations — a second, distinct
user signing off on an action the requester cannot approve alone, e.g.
approving a document template version someone else drafted);
`configuracion_audit_log` persists before/after state for critical
mutations (device status changes, template version status changes),
mirroring the shape already proven by `inventory_authorization_log`/
`inventory_audit_log` (`backend/infrastructure/db/schema/
inventory_schema.py`) — same mold, new bounded context, never a shared
table (each bounded context owns its own log, same as Inventory/Products).

Callers must mask sensitive fields before building `before_json`/
`after_json` (see `backend/security/audit/sensitive_data_redaction.py::
redact_mapping`) — this schema stores whatever JSON it's given verbatim.
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_AUTHORIZATION_LOG_DDL = f"""
    CREATE TABLE IF NOT EXISTS configuracion_authorization_log (
        id               TEXT PRIMARY KEY CHECK({_uuid('id')}),
        permission_code  TEXT NOT NULL CHECK(trim(permission_code)<>''),
        requested_by     TEXT NOT NULL CHECK(trim(requested_by)<>''),
        authorized_by    TEXT NOT NULL CHECK(trim(authorized_by)<>''),
        operation_id     TEXT NOT NULL CHECK({_uuid('operation_id')}),
        reason           TEXT NOT NULL CHECK(trim(reason)<>''),
        device_id        TEXT,
        created_at       TEXT NOT NULL
    )
"""

_AUDIT_LOG_DDL = """
    CREATE TABLE IF NOT EXISTS configuracion_audit_log (
        id             TEXT PRIMARY KEY,
        entity_type    TEXT NOT NULL,
        entity_id      TEXT NOT NULL,
        action         TEXT NOT NULL,
        user_id        TEXT,
        authorized_by  TEXT,
        operation_id   TEXT,
        before_json    TEXT,
        after_json     TEXT,
        reason         TEXT,
        branch_id      TEXT,
        occurred_at    TEXT NOT NULL,
        device_id      TEXT,
        source_module  TEXT NOT NULL DEFAULT 'configuracion'
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_config_authz_log_operation "
    "ON configuracion_authorization_log(operation_id)",
    "CREATE INDEX IF NOT EXISTS idx_config_audit_log_entity "
    "ON configuracion_audit_log(entity_type, entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_config_audit_log_occurred "
    "ON configuracion_audit_log(occurred_at)",
)


def create_configuracion_security_schema(conn) -> None:
    conn.execute(_AUTHORIZATION_LOG_DDL)
    conn.execute(_AUDIT_LOG_DDL)
    for statement in _INDEXES:
        conn.execute(statement)
