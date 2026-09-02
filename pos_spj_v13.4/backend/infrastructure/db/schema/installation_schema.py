"""Installation provisioning schema — SHELL-2.

DDL lives only here; only migration 206 may call `create_installation_schema`.
`installation` is a singleton table (exactly one row, at
`backend.shared.ids.INSTALLATION_SINGLETON_UUID`) — the app has one
provisioning lifecycle per deployed instance, not per company/branch.
"""
from __future__ import annotations

_INSTALLATION_DDL = (
    """
    CREATE TABLE IF NOT EXISTS installation (
        id                      TEXT PRIMARY KEY,
        installation_code       TEXT NOT NULL UNIQUE,
        company_id              TEXT,
        initial_branch_id       TEXT,
        workstation_id          TEXT,
        provisioning_status     TEXT NOT NULL DEFAULT 'UNINITIALIZED' CHECK (
            provisioning_status IN (
                'UNINITIALIZED', 'PROVISIONING', 'PROVISIONED',
                'LOCKED', 'RECOVERY_REQUIRED'
            )
        ),
        provisioned_at          TEXT,
        provisioned_by_user_id  TEXT,
        schema_version          TEXT,
        application_version     TEXT,
        created_at              TEXT NOT NULL,
        updated_at              TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS installation_recovery_codes (
        id              TEXT PRIMARY KEY,
        installation_id TEXT NOT NULL REFERENCES installation(id),
        code_hash       TEXT NOT NULL UNIQUE,
        status          TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (
            status IN ('ACTIVE', 'USED', 'REVOKED')
        ),
        created_at      TEXT NOT NULL,
        used_at         TEXT
    )
    """,
)

_INSTALLATION_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_installation_recovery_codes_installation "
    "ON installation_recovery_codes(installation_id, status)",
)


def create_installation_schema(conn) -> None:
    for statement in _INSTALLATION_DDL:
        conn.execute(statement)
    for index in _INSTALLATION_INDEXES:
        conn.execute(index)
