from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.health.checks import (
    ClockHealthCheck,
    DatabaseHealthCheck,
    DiskSpaceHealthCheck,
    SchemaHealthCheck,
    SecretStoreHealthCheck,
    UuidIdentityHealthCheck,
    default_health_checks,
)
from backend.bootstrap.health.health_status import HealthStatus
from backend.shared.app_paths import AppPaths
from tests.integration._born_clean_db import make_db


@pytest.fixture
def context_with_real_schema(tmp_path) -> BootstrapContext:
    ctx = BootstrapContext(db_path=Path("unused.db"))
    ctx.conn = make_db()
    ctx.app_paths = AppPaths(data_dir=tmp_path)
    return ctx


def test_database_check_unknown_without_connection():
    ctx = BootstrapContext(db_path=Path("unused.db"))
    result = DatabaseHealthCheck().check(ctx)
    assert result.status is HealthStatus.UNKNOWN


def test_database_check_healthy_for_valid_connection(context_with_real_schema):
    result = DatabaseHealthCheck().check(context_with_real_schema)
    assert result.status is HealthStatus.HEALTHY


def test_schema_check_unknown_without_connection():
    ctx = BootstrapContext(db_path=Path("unused.db"))
    result = SchemaHealthCheck().check(ctx)
    assert result.status is HealthStatus.UNKNOWN


def test_schema_check_healthy_when_critical_tables_present(context_with_real_schema):
    result = SchemaHealthCheck().check(context_with_real_schema)
    assert result.status is HealthStatus.HEALTHY


def test_schema_check_unhealthy_when_critical_table_missing():
    ctx = BootstrapContext(db_path=Path("unused.db"))
    import sqlite3

    ctx.conn = sqlite3.connect(":memory:")  # no tables at all
    result = SchemaHealthCheck().check(ctx)
    assert result.status is HealthStatus.UNHEALTHY
    assert "usuarios" in result.message


def test_uuid_identity_check_healthy_on_real_schema(context_with_real_schema):
    result = UuidIdentityHealthCheck().check(context_with_real_schema)
    assert result.status is HealthStatus.HEALTHY


def test_uuid_identity_check_detects_legacy_integer_user_id(context_with_real_schema):
    context_with_real_schema.conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, activo) "
        "VALUES ('1', 'Legacy', 'legacy_user', 'x', 'admin', 1)"
    )
    result = UuidIdentityHealthCheck().check(context_with_real_schema)
    assert result.status is HealthStatus.UNHEALTHY
    assert "no-UUIDv7" in result.message


def test_secret_store_check_healthy_with_writable_app_paths(context_with_real_schema):
    result = SecretStoreHealthCheck().check(context_with_real_schema)
    assert result.status is HealthStatus.HEALTHY


def test_disk_space_check_unknown_without_app_paths():
    ctx = BootstrapContext(db_path=Path("unused.db"))
    result = DiskSpaceHealthCheck().check(ctx)
    assert result.status is HealthStatus.UNKNOWN


def test_disk_space_check_healthy_for_real_tmp_dir(context_with_real_schema):
    result = DiskSpaceHealthCheck().check(context_with_real_schema)
    assert result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)  # depends on host free space


def test_clock_check_healthy_for_current_time():
    ctx = BootstrapContext(db_path=Path("unused.db"))
    result = ClockHealthCheck().check(ctx)
    assert result.status is HealthStatus.HEALTHY


def test_default_health_checks_returns_six_checks():
    checks = default_health_checks()
    assert len(checks) == 6
    assert {c.name for c in checks} == {
        "database", "schema", "uuid_identity", "secret_store", "disk_space", "clock",
    }
