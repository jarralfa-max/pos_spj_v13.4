"""Feature Flags schema — SET-21.

DDL lives only here; only migration 221 may call
`create_feature_flags_schema`. Backs `backend/domain/feature_flags/`
(SET-21): `feature_flags` mirrors `FeatureFlag`, `feature_flag_rules`
mirrors `FeatureFlagRule`, `feature_flag_change_requests` mirrors
`FeatureFlagChangeRequest`.

Deliberately a NEW table name (`feature_flags` already exists as the
legacy dual-schema table `repositories/feature_flag_repository.py`
detects at runtime via `PRAGMA table_info` — see that module's own
comment). Colliding with it would break the legacy consumers
(`modulos/config_modules.py`, `modulos/delivery.py`) still reading it, so
this schema uses `ff_` prefixes instead, born-clean and UUIDv7 from the
start, with no relationship to the legacy table.
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_SCOPE_TYPES = "'GLOBAL','BRANCH','USER'"
_CHANGE_STATUSES = "'PENDING_APPROVAL','APPROVED','REJECTED','APPLIED'"

_FF_FLAGS_DDL = f"""
    CREATE TABLE IF NOT EXISTS ff_flags (
        id                TEXT PRIMARY KEY CHECK({_uuid('id')}),
        code              TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        name              TEXT NOT NULL CHECK(trim(name)<>''),
        description       TEXT NOT NULL DEFAULT '',
        default_enabled   INTEGER NOT NULL DEFAULT 0 CHECK(default_enabled IN (0,1)),
        active            INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at        TEXT NOT NULL,
        updated_at        TEXT NOT NULL
    )
"""

_FF_RULES_DDL = f"""
    CREATE TABLE IF NOT EXISTS ff_rules (
        id                    TEXT PRIMARY KEY CHECK({_uuid('id')}),
        flag_id               TEXT NOT NULL REFERENCES ff_flags(id) CHECK({_uuid('flag_id')}),
        scope_type            TEXT NOT NULL CHECK(scope_type IN ({_SCOPE_TYPES})),
        scope_id              TEXT,
        enabled               INTEGER NOT NULL CHECK(enabled IN (0,1)),
        rollout_percentage    INTEGER NOT NULL DEFAULT 100 CHECK(rollout_percentage BETWEEN 0 AND 100),
        active                INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at            TEXT NOT NULL,
        updated_at            TEXT NOT NULL
    )
"""

_FF_CHANGE_REQUESTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS ff_change_requests (
        id                              TEXT PRIMARY KEY CHECK({_uuid('id')}),
        flag_id                         TEXT NOT NULL REFERENCES ff_flags(id) CHECK({_uuid('flag_id')}),
        scope_type                      TEXT NOT NULL CHECK(scope_type IN ({_SCOPE_TYPES})),
        scope_id                        TEXT,
        proposed_enabled                INTEGER NOT NULL CHECK(proposed_enabled IN (0,1)),
        proposed_rollout_percentage     INTEGER NOT NULL DEFAULT 100 CHECK(proposed_rollout_percentage BETWEEN 0 AND 100),
        requested_by_user_id            TEXT NOT NULL,
        status                          TEXT NOT NULL CHECK(status IN ({_CHANGE_STATUSES})),
        approved_by_user_id             TEXT,
        reason                          TEXT,
        created_at                      TEXT NOT NULL,
        updated_at                      TEXT NOT NULL
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_ff_flags_active ON ff_flags(active)",
    "CREATE INDEX IF NOT EXISTS idx_ff_rules_flag ON ff_rules(flag_id)",
    # At most one ACTIVE rule per (flag, scope_type, scope_id) — COALESCE
    # folds NULL scope_id (GLOBAL rules) to '' so SQLite treats it as
    # comparable rather than "always distinct", same discipline
    # `ux_print_routes_scope` (device_management, SET-8) established.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ff_rules_scope_active "
    "ON ff_rules(flag_id, scope_type, COALESCE(scope_id,'')) WHERE active=1",
    "CREATE INDEX IF NOT EXISTS idx_ff_change_requests_flag ON ff_change_requests(flag_id)",
    "CREATE INDEX IF NOT EXISTS idx_ff_change_requests_status ON ff_change_requests(status)",
)


def create_feature_flags_schema(conn) -> None:
    conn.execute(_FF_FLAGS_DDL)
    conn.execute(_FF_RULES_DDL)
    conn.execute(_FF_CHANGE_REQUESTS_DDL)
    for statement in _INDEXES:
        conn.execute(statement)
