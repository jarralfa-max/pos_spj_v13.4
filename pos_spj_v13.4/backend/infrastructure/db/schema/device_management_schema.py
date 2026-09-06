"""Device Management schema — SET-7.

DDL lives only here; only migration 211 may call
`create_device_management_schema`. Backs
`backend/domain/device_management/` (SET-7): `device_profiles` mirrors
`DeviceProfile`, `devices` mirrors `Device`,
`workstation_device_assignments` mirrors `WorkstationDeviceAssignment`.

`devices.branch_id` FKs to the existing `sucursales(id)` (same pattern as
`branch_profiles`/`workstations` in the Settings schema — a device
belongs to a branch that already exists) and
`workstation_device_assignments.workstation_id` FKs to `workstations(id)`
(migration 210) — this schema deliberately depends on Settings' schema,
not the reverse, matching the migration order (208-210 before 211).

`device_profiles` never stores a raw secret: `credential_reference` is a
name into `SecretStoreGateway` (`backend/security/secrets/`), and
`extra_parameters_json` is guarded at the domain layer
(`ConnectionProfile.create()`) against secret-looking keys before it ever
reaches this table.
"""

from __future__ import annotations

_UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


def _uuid(column: str) -> str:
    return _UUID_CHECK.format(column)


_DEVICE_TYPES = (
    "'THERMAL_PRINTER','LABEL_PRINTER','DOCUMENT_PRINTER','SCALE','BARCODE_SCANNER',"
    "'QR_SCANNER','CASH_DRAWER','PAYMENT_TERMINAL','CUSTOMER_DISPLAY','TEMPERATURE_SENSOR',"
    "'CARD_PRINTER','MOBILE_DEVICE','OTHER'"
)

_CONNECTION_TYPES = "'USB','SERIAL','BLUETOOTH','NETWORK','HTTP','WEBSOCKET','SYSTEM','VIRTUAL'"

_DEVICE_STATUSES = "'ACTIVE','INACTIVE','MAINTENANCE','BLOCKED','RETIRED'"

_ASSIGNMENT_ROLES = (
    "'PRIMARY_RECEIPT_PRINTER','SECONDARY_RECEIPT_PRINTER','LABEL_PRINTER','KITCHEN_PRINTER',"
    "'PRODUCTION_PRINTER','TRANSFER_PRINTER','SCALE','SCANNER','CASH_DRAWER',"
    "'PAYMENT_TERMINAL','CUSTOMER_DISPLAY'"
)

_DEVICE_PROFILES_DDL = f"""
    CREATE TABLE IF NOT EXISTS device_profiles (
        id                     TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        name                   TEXT NOT NULL CHECK(trim(name)<>''),
        device_type            TEXT NOT NULL CHECK(device_type IN ({_DEVICE_TYPES})),
        manufacturer           TEXT NOT NULL DEFAULT '',
        model                  TEXT NOT NULL DEFAULT '',
        connection_type        TEXT NOT NULL CHECK(connection_type IN ({_CONNECTION_TYPES})),
        serial_port_json       TEXT,
        network_endpoint_json  TEXT,
        extra_parameters_json  TEXT NOT NULL DEFAULT '{{}}',
        credential_reference   TEXT,
        capabilities_json      TEXT NOT NULL DEFAULT '[]',
        paper_profile          TEXT,
        protocol               TEXT NOT NULL DEFAULT '',
        driver_name            TEXT NOT NULL DEFAULT '',
        timeout_seconds        INTEGER NOT NULL DEFAULT 5 CHECK(timeout_seconds > 0),
        retry_max_attempts     INTEGER NOT NULL DEFAULT 3 CHECK(retry_max_attempts >= 0),
        health_check_enabled   INTEGER NOT NULL DEFAULT 1 CHECK(health_check_enabled IN (0,1)),
        active                 INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at             TEXT NOT NULL,
        updated_at             TEXT NOT NULL
    )
"""

_DEVICES_DDL = f"""
    CREATE TABLE IF NOT EXISTS devices (
        id                   TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        branch_id            TEXT NOT NULL REFERENCES sucursales(id) CHECK({_uuid('branch_id')}),
        profile_id           TEXT NOT NULL REFERENCES device_profiles(id) CHECK({_uuid('profile_id')}),
        code                 TEXT NOT NULL UNIQUE CHECK(trim(code)<>''),
        name                 TEXT NOT NULL CHECK(trim(name)<>''),
        hardware_identifier  TEXT,
        status               TEXT NOT NULL CHECK(status IN ({_DEVICE_STATUSES})),
        notes                TEXT NOT NULL DEFAULT '',
        blocked_reason       TEXT,
        created_at           TEXT NOT NULL,
        updated_at           TEXT NOT NULL
    )
"""

_ASSIGNMENTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS workstation_device_assignments (
        id                    TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        workstation_id        TEXT NOT NULL REFERENCES workstations(id) CHECK({_uuid('workstation_id')}),
        device_id             TEXT NOT NULL REFERENCES devices(id) CHECK({_uuid('device_id')}),
        role                  TEXT NOT NULL CHECK(role IN ({_ASSIGNMENT_ROLES})),
        active                INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        assigned_by_user_id   TEXT,
        assigned_at           TEXT NOT NULL,
        unassigned_at         TEXT,
        UNIQUE(device_id, workstation_id, role)
    )
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_device_profiles_active ON device_profiles(active)",
    "CREATE INDEX IF NOT EXISTS idx_devices_branch ON devices(branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status)",
    "CREATE INDEX IF NOT EXISTS idx_wda_workstation ON workstation_device_assignments(workstation_id)",
    "CREATE INDEX IF NOT EXISTS idx_wda_device ON workstation_device_assignments(device_id)",
    # §20/§62: at most one *active* device per (workstation, role) — this
    # is the constraint that actually prevents "two primary printers at
    # once", not the plain UNIQUE(device_id, workstation_id, role) above
    # (which only stops the exact same row from duplicating).
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_wda_workstation_role_active "
    "ON workstation_device_assignments(workstation_id, role) WHERE active=1",
)


def create_device_management_schema(conn) -> None:
    conn.execute(_DEVICE_PROFILES_DDL)
    conn.execute(_DEVICES_DDL)
    conn.execute(_ASSIGNMENTS_DDL)
    for statement in _INDEXES:
        conn.execute(statement)


_PRINT_ROUTES_DDL = f"""
    CREATE TABLE IF NOT EXISTS print_routes (
        id                        TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        document_type             TEXT NOT NULL CHECK(trim(document_type)<>''),
        primary_device_id         TEXT NOT NULL REFERENCES devices(id) CHECK({_uuid('primary_device_id')}),
        fallback_device_ids_json  TEXT NOT NULL DEFAULT '[]',
        branch_id                 TEXT REFERENCES sucursales(id) CHECK(branch_id IS NULL OR ({_uuid('branch_id')})),
        workstation_id            TEXT REFERENCES workstations(id) CHECK(workstation_id IS NULL OR ({_uuid('workstation_id')})),
        module                    TEXT,
        channel                   TEXT,
        active                    INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at                TEXT NOT NULL,
        updated_at                TEXT NOT NULL
    )
"""

_PRINTER_TEST_RESULTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS printer_test_results (
        id                   TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        device_id            TEXT NOT NULL REFERENCES devices(id) CHECK({_uuid('device_id')}),
        success              INTEGER NOT NULL CHECK(success IN (0,1)),
        message              TEXT NOT NULL DEFAULT '',
        tested_by_user_id    TEXT,
        tested_at            TEXT NOT NULL
    )
"""

_PRINT_ROUTING_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_print_routes_document_type ON print_routes(document_type)",
    # §25: no two routes may claim the exact same (document_type, scope
    # combination) — COALESCE folds NULL scope dimensions to '' so SQLite
    # treats them as comparable rather than "always distinct".
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_print_routes_scope ON print_routes("
    "document_type, COALESCE(branch_id,''), COALESCE(workstation_id,''),"
    " COALESCE(module,''), COALESCE(channel,''))",
    "CREATE INDEX IF NOT EXISTS idx_printer_test_results_device ON printer_test_results(device_id)",
)


def create_print_routing_schema(conn) -> None:
    """SET-8 — separate migration (212) from 211, same reasoning as
    every prior split: a shipped migration's body must not change."""
    conn.execute(_PRINT_ROUTES_DDL)
    conn.execute(_PRINTER_TEST_RESULTS_DDL)
    for statement in _PRINT_ROUTING_INDEXES:
        conn.execute(statement)


_DEVICE_TEST_RESULTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS device_test_results (
        id                   TEXT NOT NULL PRIMARY KEY CHECK({_uuid('id')}),
        device_id            TEXT NOT NULL REFERENCES devices(id) CHECK({_uuid('device_id')}),
        test_type            TEXT NOT NULL CHECK(trim(test_type)<>''),
        success              INTEGER NOT NULL CHECK(success IN (0,1)),
        message              TEXT NOT NULL DEFAULT '',
        tested_by_user_id    TEXT,
        tested_at            TEXT NOT NULL
    )
"""

_DEVICE_TEST_RESULTS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_device_test_results_device ON device_test_results(device_id)",
)


def create_scale_reader_diagnostics_schema(conn) -> None:
    """SET-9 (Básculas y lectores) — separate migration (213). Only
    `device_test_results` needs a table: `WeightReading`/`StabilityPolicy`
    are deliberately not persisted here (see their docstrings)."""
    conn.execute(_DEVICE_TEST_RESULTS_DDL)
    for statement in _DEVICE_TEST_RESULTS_INDEXES:
        conn.execute(statement)
