import sqlite3

from core.services.feature_flag_service import FeatureFlagService
from repositories.feature_flag_repository import FeatureFlagRepository


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_feature_flag_service_updates_branch_flag_through_service_boundary() -> None:
    conn = _connection()
    conn.executescript(
        """
        CREATE TABLE feature_flags(
            feature_name TEXT,
            enabled INTEGER DEFAULT 0,
            branch_id INTEGER,
            PRIMARY KEY(feature_name, branch_id)
        );
        INSERT INTO feature_flags(feature_name, enabled, branch_id) VALUES
            ('POS', 1, 2);
        """
    )
    service = FeatureFlagService(FeatureFlagRepository(conn))

    assert service.is_enabled("POS", 2) is True

    service.set_flag("POS", 2, False)

    row = conn.execute(
        "SELECT enabled FROM feature_flags WHERE feature_name=? AND branch_id=?",
        ("POS", 2),
    ).fetchone()
    assert row["enabled"] == 0
    assert service.is_enabled("POS", 2) is False


def test_feature_flag_service_updates_legacy_global_flag_and_refreshes_cache() -> None:
    conn = _connection()
    conn.executescript(
        """
        CREATE TABLE feature_flags(
            clave TEXT PRIMARY KEY,
            activo INTEGER DEFAULT 0
        );
        INSERT INTO feature_flags(clave, activo) VALUES ('RRHH', 0);
        """
    )
    service = FeatureFlagService(FeatureFlagRepository(conn))

    assert service.is_enabled("RRHH", 1) is False

    service.set_flag("RRHH", 1, True)

    row = conn.execute(
        "SELECT activo FROM feature_flags WHERE clave=?",
        ("RRHH",),
    ).fetchone()
    assert row["activo"] == 1
    assert service.is_enabled("RRHH", 1) is True
