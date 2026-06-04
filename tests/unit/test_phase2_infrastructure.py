from pathlib import Path
import sqlite3

from backend.infrastructure.db.database import DatabaseSettings, create_connection_factory
from backend.infrastructure.db.dialect import DatabaseDialect, get_dialect_capabilities
from backend.infrastructure.db.unit_of_work import DbApiUnitOfWork
from backend.infrastructure.updater.update_installer import UpdateInstaller
from backend.infrastructure.updater.update_manifest import UpdateManifest
from backend.infrastructure.updater.version_checker import VersionChecker
from backend.shared.app_paths import AppPaths


def test_app_paths_resolve_writable_exe_compatible_directories(tmp_path: Path) -> None:
    paths = AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data").ensure_directories()

    assert paths.root == (tmp_path / "app").resolve()
    assert paths.sqlite_database_path().parent == paths.database_dir
    assert paths.backups_dir.is_dir()
    assert paths.downloads_dir.is_dir()
    assert paths.manifests_dir.is_dir()


def test_database_dialect_supports_sqlite_and_postgresql_metadata() -> None:
    assert DatabaseDialect.from_url("sqlite:///tmp/spj.sqlite3") is DatabaseDialect.SQLITE
    assert DatabaseDialect.from_url("postgresql://localhost/spj") is DatabaseDialect.POSTGRESQL
    assert get_dialect_capabilities(DatabaseDialect.SQLITE).paramstyle == "qmark"
    assert get_dialect_capabilities(DatabaseDialect.POSTGRESQL).paramstyle == "pyformat"


def test_sqlite_unit_of_work_uses_injected_connection_factory() -> None:
    connection = sqlite3.connect(":memory:")
    unit_of_work = DbApiUnitOfWork(lambda: connection)

    with unit_of_work as active:
        assert active.connection is connection


def test_update_installer_creates_sqlite_backup_before_plan(tmp_path: Path) -> None:
    paths = AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data").ensure_directories()
    database_path = paths.sqlite_database_path()
    database_path.write_text("sqlite-content", encoding="utf-8")
    manifest = UpdateManifest(
        version="1.2.3",
        package_url="https://updates.example.invalid/spj-1.2.3.zip",
        checksum_sha256="abc123",
    )

    plan = UpdateInstaller(paths).plan_install(manifest, tmp_path / "spj-1.2.3.zip", database_path)

    assert plan.sqlite_backup is not None
    assert plan.sqlite_backup.destination.exists()
    assert plan.sqlite_backup.destination.read_text(encoding="utf-8") == "sqlite-content"


def test_version_checker_detects_available_update() -> None:
    manifest = UpdateManifest(
        version="2.0.0",
        package_url="https://updates.example.invalid/spj-2.0.0.zip",
        checksum_sha256="abc123",
        mandatory=True,
    )

    result = VersionChecker().check("1.9.9", manifest)

    assert result.update_available is True
    assert result.mandatory is True
