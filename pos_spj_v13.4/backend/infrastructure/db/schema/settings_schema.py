"""Configuration Governance schema — SET-3.

DDL lives only here; only migration 208 may call
`create_settings_schema`. Backs `backend/domain/settings/` (SET-2):
`configuration_definitions` mirrors `ConfigurationDefinition`,
`configuration_values` mirrors `ConfigurationValue`.

Born-clean: every id is UUIDv7 TEXT (REGLA CERO), no
`INTEGER PRIMARY KEY AUTOINCREMENT`. `value_json`/`default_value_json`/
`allowed_values_json`/`validation_schema_json` hold the typed Python value
serialized by `backend/infrastructure/db/repositories/settings/value_serialization.py`
— Decimal-valued types are stored as JSON strings (never JSON numbers, to
avoid float round-tripping money/percent values).
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_VALUE_TYPES = (
    "'BOOLEAN','STRING','INTEGER','DECIMAL','MONEY','PERCENT','DATE','TIME',"
    "'DATETIME','DURATION','ENUM','MULTI_ENUM','JSON_SCHEMA','UUID_REFERENCE',"
    "'SECRET_REFERENCE','FILE_REFERENCE','COLOR_TOKEN','TEMPLATE_REFERENCE','DEVICE_REFERENCE'"
)

_SCOPE_TYPES = (
    "'GLOBAL','COMPANY','BRANCH','WAREHOUSE','LOCATION','WORKSTATION','MODULE',"
    "'DEVICE','CHANNEL','USER','ROLE','CUSTOMER_SEGMENT','PRODUCT_CATEGORY',"
    "'PRODUCT','PROCESS','DELIVERY_ZONE'"
)

_VALUE_STATUSES = (
    "'DRAFT','PENDING_APPROVAL','APPROVED','ACTIVE','SCHEDULED','EXPIRED',"
    "'REJECTED','CANCELLED','ROLLED_BACK'"
)

_DEFINITIONS_DDL = f"""
    CREATE TABLE IF NOT EXISTS configuration_definitions (
        id                      TEXT PRIMARY KEY CHECK({_uuid('id')}),
        key                     TEXT NOT NULL UNIQUE CHECK(trim(key)<>''),
        module                  TEXT NOT NULL CHECK(trim(module)<>''),
        section                 TEXT NOT NULL DEFAULT '',
        label                   TEXT NOT NULL CHECK(trim(label)<>''),
        description             TEXT NOT NULL DEFAULT '',
        value_type              TEXT NOT NULL CHECK(value_type IN ({_VALUE_TYPES})),
        default_value_json      TEXT,
        validation_schema_json  TEXT,
        allowed_values_json     TEXT,
        allowed_scopes_json     TEXT NOT NULL CHECK(trim(allowed_scopes_json)<>''),
        default_scope           TEXT CHECK(default_scope IS NULL OR default_scope IN ({_SCOPE_TYPES})),
        inheritance_enabled     INTEGER NOT NULL DEFAULT 1 CHECK(inheritance_enabled IN (0,1)),
        override_allowed        INTEGER NOT NULL DEFAULT 1 CHECK(override_allowed IN (0,1)),
        approval_required       INTEGER NOT NULL DEFAULT 0 CHECK(approval_required IN (0,1)),
        sensitive               INTEGER NOT NULL DEFAULT 0 CHECK(sensitive IN (0,1)),
        restart_required        INTEGER NOT NULL DEFAULT 0 CHECK(restart_required IN (0,1)),
        offline_available       INTEGER NOT NULL DEFAULT 1 CHECK(offline_available IN (0,1)),
        deprecated              INTEGER NOT NULL DEFAULT 0 CHECK(deprecated IN (0,1)),
        replacement_key         TEXT,
        created_at              TEXT NOT NULL,
        updated_at              TEXT NOT NULL
    )
"""

_VALUES_DDL = f"""
    CREATE TABLE IF NOT EXISTS configuration_values (
        id                      TEXT PRIMARY KEY CHECK({_uuid('id')}),
        definition_id           TEXT NOT NULL REFERENCES configuration_definitions(id),
        scope_type              TEXT NOT NULL CHECK(scope_type IN ({_SCOPE_TYPES})),
        scope_id                TEXT,
        value_json              TEXT NOT NULL,
        effective_from          TEXT NOT NULL,
        effective_to            TEXT,
        version                 INTEGER NOT NULL CHECK(version >= 1),
        status                  TEXT NOT NULL CHECK(status IN ({_VALUE_STATUSES})),
        created_by_user_id      TEXT,
        approved_by_user_id     TEXT,
        activated_by_user_id    TEXT,
        reason                  TEXT,
        previous_version_id     TEXT REFERENCES configuration_values(id),
        operation_id            TEXT,
        created_at              TEXT NOT NULL,
        updated_at              TEXT NOT NULL,
        CHECK((scope_type='GLOBAL' AND scope_id IS NULL) OR (scope_type<>'GLOBAL' AND scope_id IS NOT NULL)),
        CHECK(effective_to IS NULL OR effective_to > effective_from)
    )
"""

_INDEXES = (
    # One version number per (definition, scope) lineage. COALESCE folds
    # GLOBAL's NULL scope_id to '' — SQLite treats distinct UNIQUE NULLs as
    # non-colliding, which would silently defeat this constraint for GLOBAL.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_configuration_values_definition_scope_version "
    "ON configuration_values(definition_id, scope_type, COALESCE(scope_id, ''), version)",
    # Idempotent writes (§62): a given operation_id may only ever produce
    # one configuration_values row.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_configuration_values_operation_id "
    "ON configuration_values(operation_id) WHERE operation_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_configuration_values_resolution "
    "ON configuration_values(definition_id, scope_type, scope_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_configuration_values_status "
    "ON configuration_values(status)",
    "CREATE INDEX IF NOT EXISTS idx_configuration_definitions_module "
    "ON configuration_definitions(module)",
)


_COMPANY_PROFILES_DDL = f"""
    CREATE TABLE IF NOT EXISTS company_profiles (
        id                      TEXT PRIMARY KEY CHECK({_uuid('id')}),
        legal_name              TEXT NOT NULL CHECK(trim(legal_name)<>''),
        commercial_name         TEXT NOT NULL DEFAULT '',
        tax_id                  TEXT NOT NULL DEFAULT '',
        business_name           TEXT NOT NULL DEFAULT '',
        logo_asset_id           TEXT CHECK(logo_asset_id IS NULL OR ({_uuid('logo_asset_id')})),
        address                 TEXT NOT NULL DEFAULT '',
        phone                   TEXT,
        email                   TEXT,
        website                 TEXT,
        social_networks_json    TEXT NOT NULL DEFAULT '{{}}',
        default_currency        TEXT NOT NULL CHECK(length(default_currency)=3),
        default_timezone        TEXT NOT NULL CHECK(trim(default_timezone)<>''),
        default_locale          TEXT NOT NULL CHECK(trim(default_locale)<>''),
        fiscal_regime_reference TEXT,
        active                  INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at              TEXT NOT NULL,
        updated_at              TEXT NOT NULL
    )
"""

# `branch_id` extends the pre-existing `sucursales` row (identity, not a
# competing table) — see backend/domain/settings/entities/branch_profile.py's
# docstring for why `sucursales` itself isn't cut over here.
_BRANCH_PROFILES_DDL = f"""
    CREATE TABLE IF NOT EXISTS branch_profiles (
        id                              TEXT PRIMARY KEY CHECK({_uuid('id')}),
        branch_id                       TEXT NOT NULL UNIQUE REFERENCES sucursales(id) CHECK({_uuid('branch_id')}),
        code                            TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        name                            TEXT NOT NULL CHECK(trim(name)<>''),
        address                         TEXT NOT NULL DEFAULT '',
        phone                           TEXT,
        timezone                        TEXT NOT NULL DEFAULT '',
        locale                          TEXT NOT NULL DEFAULT '',
        opening_time                    TEXT,
        closing_time                    TEXT,
        operation_days_json             TEXT NOT NULL DEFAULT '[]',
        warehouse_ids_json              TEXT NOT NULL DEFAULT '[]',
        default_workstation_profile_id  TEXT CHECK(default_workstation_profile_id IS NULL OR ({_uuid('default_workstation_profile_id')})),
        ticket_header                   TEXT NOT NULL DEFAULT '',
        ticket_footer                   TEXT NOT NULL DEFAULT '',
        social_links_json               TEXT NOT NULL DEFAULT '{{}}',
        map_latitude                    TEXT,
        map_longitude                   TEXT,
        map_place_id                    TEXT,
        active                          INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at                      TEXT NOT NULL,
        updated_at                      TEXT NOT NULL,
        CHECK((opening_time IS NULL AND closing_time IS NULL) OR (opening_time IS NOT NULL AND closing_time IS NOT NULL)),
        CHECK((map_latitude IS NULL) = (map_longitude IS NULL))
    )
"""

_PROFILE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_company_profiles_active ON company_profiles(active)",
    "CREATE INDEX IF NOT EXISTS idx_branch_profiles_active ON branch_profiles(active)",
)

_WORKSTATION_TYPES = (
    "'POS','BACKOFFICE','WAREHOUSE','RECEIVING','PRODUCTION','PROCESSING',"
    "'DELIVERY_COORDINATION','CUSTOMER_SERVICE','ADMINISTRATION','MOBILE','KIOSK_FUTURE'"
)

_WORKSTATION_STATUSES = "'ACTIVE','INACTIVE','MAINTENANCE','BLOCKED','RETIRED'"

_WORKSTATIONS_DDL = f"""
    CREATE TABLE IF NOT EXISTS workstations (
        id                   TEXT PRIMARY KEY CHECK({_uuid('id')}),
        branch_id            TEXT NOT NULL REFERENCES sucursales(id) CHECK({_uuid('branch_id')}),
        code                 TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        name                 TEXT NOT NULL CHECK(trim(name)<>''),
        workstation_type     TEXT NOT NULL CHECK(workstation_type IN ({_WORKSTATION_TYPES})),
        device_identifier    TEXT NOT NULL DEFAULT '',
        operating_system     TEXT NOT NULL DEFAULT '',
        application_version  TEXT NOT NULL DEFAULT '',
        status               TEXT NOT NULL CHECK(status IN ({_WORKSTATION_STATUSES})),
        offline_enabled      INTEGER NOT NULL DEFAULT 1 CHECK(offline_enabled IN (0,1)),
        last_seen_at         TEXT,
        blocked_reason       TEXT,
        created_at           TEXT NOT NULL,
        updated_at           TEXT NOT NULL
    )
"""

_WORKSTATION_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_workstations_branch ON workstations(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_workstations_status ON workstations(status)",
)


def create_settings_schema(conn) -> None:
    conn.execute(_DEFINITIONS_DDL)
    conn.execute(_VALUES_DDL)
    for statement in _INDEXES:
        conn.execute(statement)


def create_company_branch_profile_schema(conn) -> None:
    """SET-5 — separate migration (209) from `create_settings_schema`
    (208): once a migration has shipped and run on a real installation,
    the engine marks its version done and never re-diffs its body, so a
    new table set needs its own migration, not a silent addition to an
    already-executed one."""
    conn.execute(_COMPANY_PROFILES_DDL)
    conn.execute(_BRANCH_PROFILES_DDL)
    for statement in _PROFILE_INDEXES:
        conn.execute(statement)


def create_workstation_schema(conn) -> None:
    """SET-6 — separate migration (210) for the same reason
    `create_company_branch_profile_schema` is separate from 208/209: a
    shipped migration's body must not change under an installation that
    already ran it."""
    conn.execute(_WORKSTATIONS_DDL)
    for statement in _WORKSTATION_INDEXES:
        conn.execute(statement)
