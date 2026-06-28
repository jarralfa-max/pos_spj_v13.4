import sqlite3

from backend.application.queries.module_settings_query_service import ModuleSettingsQueryService

# Identidad de sucursal: UUIDv7 TEXT (sucursales.id). No hay surrogate entero ni
# columna 'uuid' puente — el branch_id se propaga como el UUID directamente.
_PRINCIPAL = "019b17a7-0000-7000-8000-000000000301"
_BODEGA = "019b17a7-0000-7000-8000-000000000302"
_CENTRO = "019b17a7-0000-7000-8000-000000000303"
_NORTE = "019b17a7-0000-7000-8000-000000000322"


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_module_settings_query_service_lists_active_branches() -> None:
    conn = _connection()
    conn.executescript(
        f"""
        CREATE TABLE sucursales(
            id TEXT PRIMARY KEY,
            nombre TEXT,
            activa INTEGER DEFAULT 1
        );
        INSERT INTO sucursales(id, nombre, activa) VALUES
            ('{_PRINCIPAL}', 'Principal', 1),
            ('{_BODEGA}', 'Bodega', 0),
            ('{_CENTRO}', 'Centro', 1);
        """
    )

    service = ModuleSettingsQueryService(conn)

    # Activas, ordenadas por nombre; el id es el UUIDv7 (sin cast a entero).
    assert service.list_active_branch_options() == [
        (_CENTRO, "Centro"),
        (_PRINCIPAL, "Principal"),
    ]


def test_module_settings_query_service_reads_legacy_global_feature_flags() -> None:
    conn = _connection()
    conn.executescript(
        f"""
        CREATE TABLE sucursales(
            id TEXT PRIMARY KEY,
            nombre TEXT,
            activa INTEGER DEFAULT 1
        );
        CREATE TABLE feature_flags(clave TEXT PRIMARY KEY, activo INTEGER DEFAULT 0);
        INSERT INTO sucursales(id, nombre, activa) VALUES ('{_PRINCIPAL}', 'Principal', 1);
        INSERT INTO feature_flags(clave, activo) VALUES ('POS', 1), ('RRHH', 0);
        """
    )

    service = ModuleSettingsQueryService(conn)

    # Schema legacy global (sin branch): el branch UUID se ignora.
    assert service.get_branch_feature_flags(_PRINCIPAL) == {"POS": True, "RRHH": False}


def test_module_settings_query_service_reads_branch_specific_flags_by_uuid() -> None:
    conn = _connection()
    conn.executescript(
        f"""
        CREATE TABLE sucursales(
            id TEXT PRIMARY KEY,
            nombre TEXT,
            activa INTEGER DEFAULT 1
        );
        CREATE TABLE feature_flags(
            feature_name TEXT,
            enabled INTEGER DEFAULT 0,
            branch_id TEXT,
            PRIMARY KEY(feature_name, branch_id)
        );
        INSERT INTO sucursales(id, nombre, activa) VALUES
            ('{_PRINCIPAL}', 'Principal', 1),
            ('{_NORTE}', 'Norte', 1);
        -- branch_id '0' = default global; el UUID de Norte tiene prioridad.
        INSERT INTO feature_flags(feature_name, enabled, branch_id) VALUES
            ('POS', 0, '0'),
            ('POS', 1, '{_NORTE}'),
            ('DELIVERY', 1, '0');
        """
    )

    service = ModuleSettingsQueryService(conn)

    assert service.get_branch_feature_flags(_NORTE) == {
        "POS": True,
        "DELIVERY": True,
    }
