import sqlite3

from backend.application.queries.module_settings_query_service import ModuleSettingsQueryService


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_module_settings_query_service_lists_active_branches() -> None:
    conn = _connection()
    conn.executescript(
        """
        CREATE TABLE sucursales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            nombre TEXT,
            activa INTEGER DEFAULT 1
        );
        INSERT INTO sucursales(uuid, nombre, activa) VALUES
            ('019b17a7-0000-7000-8000-000000000301', 'Principal', 1),
            ('019b17a7-0000-7000-8000-000000000302', 'Bodega', 0),
            ('019b17a7-0000-7000-8000-000000000303', 'Centro', 1);
        """
    )

    service = ModuleSettingsQueryService(conn)

    assert service.list_active_branch_options() == [(3, "Centro"), (1, "Principal")]


def test_module_settings_query_service_reads_legacy_feature_flags_by_branch_row_id() -> None:
    conn = _connection()
    conn.executescript(
        """
        CREATE TABLE sucursales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            nombre TEXT,
            activa INTEGER DEFAULT 1
        );
        CREATE TABLE feature_flags(clave TEXT PRIMARY KEY, activo INTEGER DEFAULT 0);
        INSERT INTO sucursales(uuid, nombre, activa) VALUES
            ('019b17a7-0000-7000-8000-000000000311', 'Principal', 1);
        INSERT INTO feature_flags(clave, activo) VALUES ('POS', 1), ('RRHH', 0);
        """
    )

    service = ModuleSettingsQueryService(conn)

    assert service.get_branch_feature_flags(1) == {"POS": True, "RRHH": False}


def test_module_settings_query_service_accepts_branch_uuid_for_read_side_lookup() -> None:
    conn = _connection()
    conn.executescript(
        """
        CREATE TABLE sucursales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            nombre TEXT,
            activa INTEGER DEFAULT 1
        );
        CREATE TABLE feature_flags(
            feature_name TEXT,
            enabled INTEGER DEFAULT 0,
            branch_id INTEGER,
            PRIMARY KEY(feature_name, branch_id)
        );
        INSERT INTO sucursales(uuid, nombre, activa) VALUES
            ('019b17a7-0000-7000-8000-000000000321', 'Principal', 1),
            ('019b17a7-0000-7000-8000-000000000322', 'Norte', 1);
        INSERT INTO feature_flags(feature_name, enabled, branch_id) VALUES
            ('POS', 0, 0),
            ('POS', 1, 2),
            ('DELIVERY', 1, 0);
        """
    )

    service = ModuleSettingsQueryService(conn)

    assert service.get_branch_feature_flags("019b17a7-0000-7000-8000-000000000322") == {
        "POS": True,
        "DELIVERY": True,
    }
