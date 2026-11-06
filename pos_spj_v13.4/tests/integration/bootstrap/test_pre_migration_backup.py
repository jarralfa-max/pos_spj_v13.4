"""SDLC-ARQ-INST-001 — ninguna migración al arrancar sin respaldo verificado.

El actualizador respalda antes de instalar, pero el Setup manual y el atajo
«Reparar» no pasan por él: las migraciones corren en el siguiente arranque. Estas
pruebas ejercitan la secuencia real de arranque sobre archivos en un directorio
temporal; sólo la lista de migraciones se sustituye cuando hace falta una que
falle.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import types
from unittest.mock import Mock

import pytest

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.desktop_application_bootstrapper import DesktopApplicationBootstrapper
from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence
from backend.bootstrap.steps.database_integrity_step import DatabaseIntegrityStep
from backend.bootstrap.steps.pre_migration_backup_step import PreMigrationBackupStep
from backend.infrastructure.db.sqlite_backup import SQLiteBackupService
import migrations.engine as engine

_APPLIED_MODULE = "migrations.fake_900_applied"
_FAILING_MODULE = "migrations.fake_901_fails"


def _station_database(path: Path, *, applied=("000",)) -> Path:
    """Base de una sucursal, con sus últimas ventas todavía en el -wal."""
    connection = sqlite3.connect(str(path))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE sales (id TEXT PRIMARY KEY, total TEXT)")
    connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
    connection.executemany("INSERT INTO schema_migrations VALUES (?)", [(v,) for v in applied])
    connection.executemany("INSERT INTO sales VALUES (?, ?)",
                           [(f"s-{i}", "10.00") for i in range(12)])
    connection.commit()
    connection.close()
    return path


def _tables(path: Path) -> set[str]:
    connection = sqlite3.connect(str(path))
    try:
        return {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        connection.close()


def _count(path: Path, sql: str) -> int:
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute(sql).fetchone()[0]
    finally:
        connection.close()


@pytest.fixture
def failing_migration(monkeypatch):
    """Dos migraciones pendientes: la 900 se aplica y la 901 revienta, que es
    justo lo que deja una base a medio migrar."""
    calls: list[str] = []

    def applied(connection):
        calls.append("900")
        connection.execute("CREATE TABLE added_by_900 (x)")
        connection.execute("DELETE FROM sales WHERE id = 's-0'")
        connection.commit()

    def fails(connection):
        calls.append("901")
        raise RuntimeError("la migración 901 explotó")

    for name, run in ((_APPLIED_MODULE, applied), (_FAILING_MODULE, fails)):
        module = types.ModuleType(name)
        module.run = run
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(engine, "MIGRATIONS", [
        engine.MIGRATIONS[0],
        engine._Migration("900", _APPLIED_MODULE),
        engine._Migration("901", _FAILING_MODULE),
    ])
    return calls


def test_failed_migration_leaves_a_restorable_database(tmp_path, failing_migration):
    database = _station_database(tmp_path / "spj.db")
    backups = tmp_path / "backups"

    result = run_database_bootstrap_sequence(database, backups_dir=backups)
    result.context.conn.close()

    assert result.success is False
    assert result.failed_step().step_name == "database_migration"
    assert failing_migration == ["900", "901"]
    # La base quedó a medio migrar: sin respaldo, esa venta ya no existiría.
    assert "added_by_900" in _tables(database)
    assert _count(database, "SELECT COUNT(*) FROM sales") == 11

    copies = list(backups.glob("*pre-migration-*.db"))
    assert len(copies) == 1
    assert copies[0].with_name(copies[0].name + ".json").is_file()
    # Quien ve el error sabe dónde está el respaldo.
    assert str(copies[0]) in result.failed_step().message

    SQLiteBackupService().restore(copies[0], database)
    assert _count(database, "SELECT COUNT(*) FROM sales") == 12
    assert "added_by_900" not in _tables(database)
    assert _count(database, "SELECT COUNT(*) FROM schema_migrations") == 1


def test_backup_failure_stops_before_any_migration_and_explains(tmp_path, failing_migration):
    database = _station_database(tmp_path / "spj.db")
    occupied = tmp_path / "backups"
    occupied.write_text("no es una carpeta", encoding="utf-8")

    result = run_database_bootstrap_sequence(database, backups_dir=occupied)
    result.context.conn.close()

    assert result.success is False
    failed = result.failed_step()
    assert failed.step_name == "pre_migration_backup"
    assert "No se migró" in failed.message
    assert failing_migration == []
    assert "added_by_900" not in _tables(database)
    assert _count(database, "SELECT COUNT(*) FROM schema_migrations") == 1
    assert _count(database, "SELECT COUNT(*) FROM sales") == 12


def _run_backup_step(database: Path, backups: Path):
    context = BootstrapContext(db_path=database, backups_dir=backups)
    result = DesktopApplicationBootstrapper(
        [DatabaseIntegrityStep(), PreMigrationBackupStep()]).bootstrap(context)
    context.conn.close()
    return result, context


def test_repair_of_the_same_version_makes_no_backup(tmp_path, monkeypatch):
    # «Reparar» reinstala la misma versión: nada pendiente, nada que respaldar.
    monkeypatch.setattr(engine, "MIGRATIONS", [engine.MIGRATIONS[0]])
    database = _station_database(tmp_path / "spj.db")
    backups = tmp_path / "backups"

    result, context = _run_backup_step(database, backups)

    assert result.success is True
    assert context.pre_migration_backup is None
    assert not backups.exists()


def test_brand_new_database_has_nothing_to_back_up(tmp_path):
    backups = tmp_path / "backups"
    result, context = _run_backup_step(tmp_path / "nueva.db", backups)
    assert result.success is True
    assert context.pre_migration_backup is None
    assert not backups.exists()


def test_database_never_tracked_by_the_engine_is_backed_up(tmp_path, monkeypatch):
    # Datos sin `schema_migrations`: todas las migraciones están pendientes.
    database = tmp_path / "spj.db"
    connection = sqlite3.connect(str(database))
    connection.execute("CREATE TABLE sales (id TEXT PRIMARY KEY)")
    connection.execute("INSERT INTO sales VALUES ('s-1')")
    connection.commit()
    connection.close()

    result, context = _run_backup_step(database, tmp_path / "backups")

    assert result.success is True
    assert context.pre_migration_backup is not None
    assert context.pre_migration_backup.is_file()


def test_real_pending_migration_is_backed_up_and_applied(tmp_path, monkeypatch):
    """Una actualización real: base migrada hasta la penúltima, binario con la
    última. Corre con el motor y las migraciones de verdad."""
    every_migration = list(engine.MIGRATIONS)
    database = tmp_path / "spj.db"
    monkeypatch.setattr(engine, "MIGRATIONS", every_migration[:-1])
    first_boot = run_database_bootstrap_sequence(database, backups_dir=tmp_path / "backups")
    assert first_boot.success, first_boot.failed_step()
    first_boot.context.conn.close()
    assert not (tmp_path / "backups").exists()

    monkeypatch.setattr(engine, "MIGRATIONS", every_migration)
    second_boot = run_database_bootstrap_sequence(database, backups_dir=tmp_path / "backups")
    assert second_boot.success, second_boot.failed_step()
    second_boot.context.conn.close()

    backup = second_boot.context.pre_migration_backup
    assert backup is not None and backup.parent == tmp_path / "backups"
    latest = every_migration[-1].version
    assert _count(backup, f"SELECT COUNT(*) FROM schema_migrations WHERE version='{latest}'") == 0
    assert _count(database, f"SELECT COUNT(*) FROM schema_migrations WHERE version='{latest}'") == 1

    third_boot = run_database_bootstrap_sequence(database, backups_dir=tmp_path / "backups")
    assert third_boot.success, third_boot.failed_step()
    third_boot.context.conn.close()
    assert third_boot.context.pre_migration_backup is None


def test_without_a_declared_folder_the_backup_sits_beside_the_database(tmp_path, failing_migration):
    # Quien llame sin decir dónde respaldar sigue protegido.
    database = _station_database(tmp_path / "spj.db")
    result = run_database_bootstrap_sequence(database)
    result.context.conn.close()
    assert list((tmp_path / "backups").glob("*pre-migration-*.db"))


def test_self_test_backs_up_into_the_stations_folder(tmp_path, monkeypatch):
    from backend.bootstrap import run_database_bootstrap, self_test
    from backend.shared.app_paths import LAYOUT_INSTALLED, AppPaths
    from backend.shared.install_config import InstallConfig

    paths = AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data",
                     layout=LAYOUT_INSTALLED, install_config=InstallConfig(),
                     database_file=tmp_path / "data" / "db" / "spj.db")
    sequence = Mock(return_value=types.SimpleNamespace(
        success=False, failed_step=lambda: None, context=types.SimpleNamespace(conn=None)))
    monkeypatch.setattr(run_database_bootstrap, "run_database_bootstrap_sequence", sequence)

    self_test.run_self_test(paths)

    assert sequence.call_args.kwargs["backups_dir"] == paths.backups_dir


def test_desktop_start_backs_up_into_the_stations_folder(tmp_path, monkeypatch):
    from backend.bootstrap import run_database_bootstrap
    import backend.infrastructure.db.connection as db_connection
    from frontend.desktop import app
    from backend.shared.app_paths import LAYOUT_INSTALLED, AppPaths
    from backend.shared.install_config import InstallConfig

    paths = AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data",
                     layout=LAYOUT_INSTALLED, install_config=InstallConfig())
    monkeypatch.setattr(app, "PATHS", paths)
    monkeypatch.setattr(app, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(db_connection, "set_db_path", lambda path: None)
    sequence = Mock(return_value=types.SimpleNamespace(
        success=True, warnings=(), final_state=types.SimpleNamespace(value="RUNNING"),
        context=types.SimpleNamespace(conn=None)))
    monkeypatch.setattr(run_database_bootstrap, "run_database_bootstrap_sequence", sequence)

    app._prepare_database()

    assert sequence.call_args.kwargs["backups_dir"] == paths.backups_dir
