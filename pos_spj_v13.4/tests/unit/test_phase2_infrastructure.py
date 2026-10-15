from pathlib import Path
import sqlite3

from backend.domain.software_distribution.semantic_version import SemanticVersion
from backend.infrastructure.db.database import DatabaseSettings, create_connection_factory
from backend.infrastructure.db.dialect import DatabaseDialect, get_dialect_capabilities
from backend.infrastructure.db.sqlite_backup import SQLiteBackupService
from backend.infrastructure.db.unit_of_work import DbApiUnitOfWork
from backend.shared.app_paths import LAYOUT_INSTALLED, AppPaths


def test_app_paths_resolve_writable_exe_compatible_directories(tmp_path: Path) -> None:
    paths = AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data",
                     layout=LAYOUT_INSTALLED).ensure_directories()

    assert paths.root == (tmp_path / "app").resolve()
    assert paths.database_path.parent == paths.database_dir
    assert paths.database_path.name == "spj_pos_database.db"
    assert paths.backups_dir.is_dir()
    assert paths.downloads_dir.is_dir()
    assert paths.manifests_dir.is_dir()


def test_api_settings_point_at_the_same_database_as_the_desktop(tmp_path: Path) -> None:
    paths = AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data",
                     layout=LAYOUT_INSTALLED)
    settings = DatabaseSettings.sqlite(paths)
    assert settings.database_url == f"sqlite:///{paths.database_path}"


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


def test_sqlite_backup_before_update_is_verified(tmp_path: Path) -> None:
    database = tmp_path / "spj_pos_database.db"
    connection = sqlite3.connect(str(database))
    connection.execute("CREATE TABLE sales (id TEXT PRIMARY KEY)")
    connection.execute("INSERT INTO sales VALUES ('s1')")
    connection.commit()
    connection.close()

    backup = SQLiteBackupService().create(database, tmp_path / "backups", label="pre-update-1.2.3")

    assert backup.path.exists() and backup.row_counts == {"sales": 1}
    assert backup.metadata_path.exists()


def test_semantic_version_detects_available_update() -> None:
    assert SemanticVersion.parse("2.0.0") > SemanticVersion.parse("1.9.9")
    assert SemanticVersion.parse("13.4.0-rc1") < SemanticVersion.parse("13.4.0")
