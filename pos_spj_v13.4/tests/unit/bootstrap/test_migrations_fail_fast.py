"""Failures must stop the real migration engine before any later migration."""
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

from migrations import engine
from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapSeverity
from backend.bootstrap.desktop_application_bootstrapper import DesktopApplicationBootstrapper
from backend.bootstrap.steps.database_migration_step import DatabaseMigrationStep


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE probe (value TEXT)")
    connection.commit()
    yield connection
    connection.close()


def register(monkeypatch, *functions):
    entries = []
    for index, fn in enumerate(functions):
        name = f"remediation_migration_{index}"
        module = ModuleType(name)
        if fn is not None:
            module.run = fn
        monkeypatch.setitem(sys.modules, name, module)
        entries.append(engine._Migration(str(index), name))
    monkeypatch.setattr(engine, "MIGRATIONS", entries)


def test_missing_migration_is_fatal(conn, monkeypatch):
    monkeypatch.setattr(engine, "MIGRATIONS", [engine._Migration("missing", "missing_required_spj_migration")])
    with pytest.raises(RuntimeError) as error:
        engine.up(conn)
    assert type(error.value).__name__ == "MigrationImportError"
    assert isinstance(error.value.__cause__, ImportError)


def test_base_schema_does_not_swallow_required_block_failure(conn):
    from migrations import m000_base_schema

    def failed(db):
        raise ValueError("required block failed")

    with pytest.raises(RuntimeError):
        m000_base_schema._safe(conn, failed, "required")


def test_fresh_database_completes_all_required_migrations_without_legacy_cash_tables():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    try:
        engine.up(db)
        versions = {row[0] for row in db.execute("SELECT version FROM schema_migrations")}
        assert versions == {migration.version for migration in engine.MIGRATIONS}
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "cash_registers" in tables
        assert {"cierres_caja", "movimientos_caja"}.isdisjoint(tables)
        assert db.execute("SELECT usuario FROM usuarios").fetchall() == []
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


@pytest.mark.parametrize("contract", [None, "not callable"])
def test_missing_migration_contract_is_fatal(conn, monkeypatch, contract):
    register(monkeypatch, contract)
    with pytest.raises(RuntimeError) as error:
        engine.up(conn)
    assert type(error.value).__name__ == "MigrationContractError"


def test_failed_migration_stops_sequence_and_is_not_marked_done(conn, monkeypatch):
    calls = []

    def first(db):
        calls.append("first")
        db.execute("INSERT INTO probe VALUES ('first')")

    def failed(db):
        calls.append("failed")
        db.execute("INSERT INTO probe VALUES ('must roll back')")
        raise ValueError("invalid schema")

    def later(db):
        calls.append("later")

    register(monkeypatch, first, failed, later)
    with pytest.raises(RuntimeError) as error:
        engine.up(conn)
    assert type(error.value).__name__ == "MigrationExecutionError"
    assert isinstance(error.value.__cause__, ValueError)
    assert calls == ["first", "failed"]
    assert conn.execute("SELECT value FROM probe").fetchall() == [("first",)]
    assert conn.execute("SELECT version FROM schema_migrations").fetchall() == [("0",)]


def test_failed_commit_rolls_back_done_marker_and_stops_sequence(monkeypatch):
    class CommitFailure(sqlite3.Connection):
        fail_commit = False

        def commit(self):
            if self.fail_commit:
                raise sqlite3.OperationalError("disk unavailable")
            return super().commit()

    db = sqlite3.connect(":memory:", factory=CommitFailure)
    db.execute("CREATE TABLE probe (value TEXT)")
    db.commit()
    calls = []

    def failed(connection):
        connection.execute("INSERT INTO probe VALUES ('rollback')")
        connection.fail_commit = True

    register(monkeypatch, failed, lambda connection: calls.append("later"))
    try:
        with pytest.raises(RuntimeError) as error:
            engine.up(db)
        assert type(error.value).__name__ == "MigrationExecutionError"
        assert db.execute("SELECT * FROM schema_migrations").fetchall() == []
        assert db.execute("SELECT * FROM probe").fetchall() == []
        assert calls == []
    finally:
        db.close()


def test_bootstrap_does_not_start_ui_after_schema_failure(conn, monkeypatch):
    def failed(db):
        raise ValueError("schema invalid")

    register(monkeypatch, failed)

    class UiStep:
        name = "ui"
        called = False

        def run(self, context):
            self.called = True
            raise AssertionError("UI must never be reached")

    ui = UiStep()
    context = BootstrapContext(db_path=Path("unused.db"))
    context.conn = conn
    result = DesktopApplicationBootstrapper([DatabaseMigrationStep(), ui]).bootstrap(context)
    assert not ui.called
    assert not result.success
    assert result.step_results[0].severity is BootstrapSeverity.FATAL
    assert result.failed_step().step_name == "database_migration"
