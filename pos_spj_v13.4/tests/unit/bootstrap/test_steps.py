import sqlite3
from pathlib import Path

import pytest

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapSeverity
from backend.bootstrap.steps.application_paths_step import ApplicationPathsStep
from backend.bootstrap.steps.database_integrity_step import DatabaseIntegrityStep
from backend.bootstrap.steps.database_migration_step import DatabaseMigrationStep
from backend.bootstrap.steps.environment_validation_step import EnvironmentValidationStep
from backend.bootstrap.steps.installation_state_step import InstallationStateStep
from backend.bootstrap.steps.schema_validation_step import SchemaValidationStep
from backend.security.provisioning.installation import ProvisioningStatus
from tests.integration._born_clean_db import make_db


# ── EnvironmentValidationStep ────────────────────────────────────────────────

def test_environment_validation_succeeds_on_current_interpreter():
    result = EnvironmentValidationStep().run(BootstrapContext(db_path=Path("unused.db")))
    assert result.success is True
    assert result.severity is BootstrapSeverity.INFO


def test_environment_validation_fails_below_minimum_python(monkeypatch):
    import backend.bootstrap.steps.environment_validation_step as mod

    monkeypatch.setattr(mod.sys, "version_info", (3, 8, 0))
    result = EnvironmentValidationStep().run(BootstrapContext(db_path=Path("unused.db")))
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL


# ── ApplicationPathsStep ─────────────────────────────────────────────────────

def test_application_paths_step_creates_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("SPJ_APP_DATA_DIR", str(tmp_path / "spj_data"))
    context = BootstrapContext(db_path=Path("unused.db"))
    result = ApplicationPathsStep().run(context)

    assert result.success is True
    assert context.app_paths is not None
    assert context.app_paths.user_data_dir.exists()
    assert context.app_paths.database_dir.exists()


# ── DatabaseIntegrityStep ────────────────────────────────────────────────────

def test_database_integrity_step_ok_for_new_database(tmp_path):
    context = BootstrapContext(db_path=tmp_path / "new.db")
    result = DatabaseIntegrityStep().run(context)

    assert result.success is True
    assert context.conn is not None


def test_database_integrity_step_ok_for_valid_existing_database(tmp_path):
    db_path = tmp_path / "existing.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (id TEXT)")
    conn.commit()
    conn.close()

    context = BootstrapContext(db_path=db_path)
    result = DatabaseIntegrityStep().run(context)

    assert result.success is True
    assert context.conn is not None


def test_database_integrity_step_fatal_for_corrupted_file(tmp_path):
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"this is not a sqlite database file at all, just garbage bytes" * 10)

    context = BootstrapContext(db_path=db_path)
    result = DatabaseIntegrityStep().run(context)

    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL


# ── DatabaseMigrationStep ────────────────────────────────────────────────────

def test_database_migration_step_fatal_without_connection():
    context = BootstrapContext(db_path=Path("unused.db"))
    result = DatabaseMigrationStep().run(context)
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL


def test_database_migration_step_ok_when_engine_succeeds(monkeypatch):
    import migrations.engine as real_engine

    monkeypatch.setattr(real_engine, "up", lambda conn: None)
    context = BootstrapContext(db_path=Path("unused.db"))
    context.conn = sqlite3.connect(":memory:")

    result = DatabaseMigrationStep().run(context)
    assert result.success is True


def test_database_migration_step_fatal_when_engine_raises(monkeypatch):
    import migrations.engine as real_engine

    def _boom(conn):
        raise RuntimeError("migration engine exploded")

    monkeypatch.setattr(real_engine, "up", _boom)
    context = BootstrapContext(db_path=Path("unused.db"))
    context.conn = sqlite3.connect(":memory:")

    result = DatabaseMigrationStep().run(context)
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL
    assert "exploded" in result.technical_details


# ── SchemaValidationStep ─────────────────────────────────────────────────────

@pytest.fixture
def real_schema_context() -> BootstrapContext:
    context = BootstrapContext(db_path=Path("unused.db"))
    context.conn = make_db()
    return context


def test_schema_validation_fatal_without_connection():
    context = BootstrapContext(db_path=Path("unused.db"))
    result = SchemaValidationStep().run(context)
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL


def test_schema_validation_fatal_when_critical_table_missing():
    context = BootstrapContext(db_path=Path("unused.db"))
    context.conn = sqlite3.connect(":memory:")  # empty schema
    result = SchemaValidationStep().run(context)
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL


def test_schema_validation_ok_on_real_schema_with_full_coverage(monkeypatch, real_schema_context):
    monkeypatch.setattr(
        "scripts.verify_tables.verificar_tablas",
        lambda db_path: {"faltantes": [], "cobertura_pct": 100.0},
    )
    result = SchemaValidationStep().run(real_schema_context)
    assert result.success is True
    assert result.severity is BootstrapSeverity.INFO


def test_schema_validation_warning_on_incomplete_broad_coverage(monkeypatch, real_schema_context):
    monkeypatch.setattr(
        "scripts.verify_tables.verificar_tablas",
        lambda db_path: {"faltantes": ["empleados"], "cobertura_pct": 90.0},
    )
    result = SchemaValidationStep().run(real_schema_context)
    assert result.success is True
    assert result.severity is BootstrapSeverity.WARNING
    assert "empleados" in result.message


def test_schema_validation_fatal_on_invalid_identity_constant(monkeypatch, real_schema_context):
    import backend.bootstrap.steps.schema_validation_step as mod

    monkeypatch.setattr(mod, "INSTALL_BRANCH_UUID", "not-a-uuid")
    result = SchemaValidationStep().run(real_schema_context)
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL
    assert "UUIDv7" in result.message


def test_schema_validation_fatal_on_leftover_integer_primary_key(monkeypatch, real_schema_context):
    # A leftover un-cut legacy table (SHELL-4: assert_uuid_identity scans the
    # *whole* database, not just the sentinel constants).
    monkeypatch.setattr(
        "scripts.verify_tables.verificar_tablas",
        lambda db_path: {"faltantes": [], "cobertura_pct": 100.0},
    )
    real_schema_context.conn.execute(
        "CREATE TABLE legacy_un_cut_table (id INTEGER PRIMARY KEY, nombre TEXT)"
    )
    result = SchemaValidationStep().run(real_schema_context)
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL
    assert "legacy_un_cut_table" in result.message


# ── InstallationStateStep ────────────────────────────────────────────────────

def test_installation_state_step_fatal_without_connection():
    context = BootstrapContext(db_path=Path("unused.db"))
    result = InstallationStateStep().run(context)
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL


def test_installation_state_step_resolves_uninitialized_on_fresh_schema(real_schema_context):
    result = InstallationStateStep().run(real_schema_context)
    assert result.success is True
    assert real_schema_context.installation_status is ProvisioningStatus.UNINITIALIZED
