"""Consistent SQLite backups under WAL, one-time legacy relocation and the
cross-process instance lock — on real files in a temporary folder."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from backend.infrastructure.db.database_relocation import (
    LegacyDatabaseRelocator,
    RelocationStatus,
)
from backend.infrastructure.db.sqlite_backup import (
    BackupVerificationError,
    SQLiteBackupService,
)
from backend.infrastructure.runtime.instance_lock import InstanceLock
from backend.shared.app_paths import LAYOUT_INSTALLED, LAYOUT_SOURCE, AppPaths
from backend.shared.install_config import InstallConfig

from ._helpers import count_sales, make_wal_database

PACKAGE_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _no_path_overrides(monkeypatch):
    for name in ("SPJ_DB_PATH", "SPJ_LEGACY_DB_PATH", "SPJ_APP_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)


# ── backups ────────────────────────────────────────────────────────────────
def test_backup_captures_committed_rows_still_in_the_wal(tmp_path):
    database = tmp_path / "live.db"
    writer = make_wal_database(database, rows=40)
    try:
        assert (tmp_path / "live.db-wal").stat().st_size > 0  # data not checkpointed
        backup = SQLiteBackupService(app_version="13.4.0").create(
            database, tmp_path / "backups", label="pre-update-13.5.0")
    finally:
        writer.close()
    assert count_sales(backup.path) == 40
    assert backup.schema_version == 337
    assert backup.row_counts["sales"] == 40
    sidecar = json.loads(backup.metadata_path.read_text(encoding="utf-8"))
    assert sidecar["sha256"] == backup.sha256 and sidecar["app_version"] == "13.4.0"
    assert not list((tmp_path / "backups").glob("*.partial"))
    # An archive is one self-contained file.
    check = sqlite3.connect(str(backup.path))
    assert check.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    check.close()


def test_backup_while_another_connection_keeps_writing(tmp_path):
    database = tmp_path / "busy.db"
    writer = make_wal_database(database, rows=10)
    try:
        writer.execute("INSERT INTO sales VALUES ('later', 1)")
        writer.commit()
        backup = SQLiteBackupService().create(database, tmp_path / "b", label="live",
                                              quiescent=False)
    finally:
        writer.close()
    assert count_sales(backup.path) in (10, 11)


def test_restore_brings_back_the_backup_and_detects_tampering(tmp_path):
    database = tmp_path / "db.sqlite"
    make_wal_database(database, rows=5).close()
    service = SQLiteBackupService()
    backup = service.create(database, tmp_path / "b", label="pre")
    # "Migration" that goes wrong afterwards:
    connection = sqlite3.connect(str(database))
    connection.execute("DELETE FROM sales")
    connection.execute("CREATE TABLE half_migrated (x)")
    connection.commit()
    connection.close()
    service.restore(backup.path, database)
    assert count_sales(database) == 5
    tables = {r[0] for r in sqlite3.connect(str(database)).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "half_migrated" not in tables
    # A modified backup is never restored.
    with open(backup.path, "r+b") as handle:
        handle.seek(-10, 2)
        handle.write(b"0123456789")
    with pytest.raises((BackupVerificationError, sqlite3.DatabaseError)):
        service.restore(backup.path, database)


def test_restore_over_an_unreadable_target_keeps_the_damaged_file(tmp_path):
    database = tmp_path / "db.sqlite"
    make_wal_database(database, rows=3).close()
    service = SQLiteBackupService()
    backup = service.create(database, tmp_path / "b", label="pre")
    database.write_bytes(b"this is not sqlite" * 100)
    service.restore(backup.path, database)
    assert count_sales(database) == 3
    assert list(tmp_path.glob("db.sqlite.damaged-*"))


# ── relocation ─────────────────────────────────────────────────────────────
def _installed_paths(tmp_path, *, legacy: list[Path] | None = None) -> AppPaths:
    config = InstallConfig(data_scope="user", legacy_database_paths=tuple(
        str(p) for p in (legacy or ())))
    return AppPaths(base_dir=tmp_path / "Program Files" / "SPJ", data_dir=tmp_path / "ProgramData",
                    layout=LAYOUT_INSTALLED, install_config=config)


def test_source_checkout_never_relocates(tmp_path):
    paths = AppPaths(base_dir=tmp_path / "src", data_dir=tmp_path / "data", layout=LAYOUT_SOURCE)
    assert paths.database_path == tmp_path / "src" / "data" / "spj_pos_database.db"
    assert LegacyDatabaseRelocator(paths).run().status is RelocationStatus.NOT_APPLICABLE


def test_fresh_installation_starts_clean(tmp_path):
    result = LegacyDatabaseRelocator(_installed_paths(tmp_path)).run()
    assert result.status is RelocationStatus.FRESH and not result.blocks_startup


def test_legacy_database_is_moved_once_with_backup_and_verification(tmp_path):
    legacy = tmp_path / "old-source" / "data" / "spj_pos_database.db"
    make_wal_database(legacy, rows=30).close()
    paths = _installed_paths(tmp_path, legacy=[legacy])
    result = LegacyDatabaseRelocator(paths).run()
    assert result.status is RelocationStatus.RELOCATED, result.message
    assert count_sales(paths.database_path) == 30
    assert not legacy.exists()
    archived = list(legacy.parent.glob("spj_pos_database.db.relocated-*"))
    assert any(p.suffix != ".txt" for p in archived)
    assert result.backup is not None and count_sales(result.backup.path) == 30
    assert result.backup.path.name.startswith("spj_pos_database-pre-relocation-")
    assert result.backup.path.suffix == ".db"
    marker = json.loads((paths.database_dir / "relocation.json").read_text(encoding="utf-8"))
    assert marker["from"] == str(legacy)
    # Second start: in place, nothing moves again.
    assert LegacyDatabaseRelocator(paths).run().status is RelocationStatus.IN_PLACE


def test_two_databases_block_the_start(tmp_path):
    legacy = tmp_path / "old" / "spj_pos_database.db"
    make_wal_database(legacy, rows=2).close()
    paths = _installed_paths(tmp_path, legacy=[legacy])
    make_wal_database(paths.database_path, rows=1).close()
    result = LegacyDatabaseRelocator(paths).run()
    assert result.status is RelocationStatus.CONFLICT and result.blocks_startup
    assert legacy.exists() and count_sales(paths.database_path) == 1  # nothing touched


def test_several_legacy_candidates_block_the_start(tmp_path):
    first, second = tmp_path / "a" / "x.db", tmp_path / "b" / "y.db"
    make_wal_database(first).close()
    make_wal_database(second).close()
    result = LegacyDatabaseRelocator(_installed_paths(tmp_path, legacy=[first, second])).run()
    assert result.status is RelocationStatus.CONFLICT


def test_vanished_relocated_database_never_becomes_an_empty_one(tmp_path):
    legacy = tmp_path / "old" / "spj_pos_database.db"
    make_wal_database(legacy, rows=4).close()
    paths = _installed_paths(tmp_path, legacy=[legacy])
    assert LegacyDatabaseRelocator(paths).run().status is RelocationStatus.RELOCATED
    paths.database_path.unlink()
    result = LegacyDatabaseRelocator(paths).run()
    assert result.status is RelocationStatus.MISSING_AFTER_RELOCATION and result.blocks_startup
    assert not paths.database_path.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows refuses to rename an open file")
def test_legacy_database_open_elsewhere_is_left_intact(tmp_path):
    legacy = tmp_path / "old" / "spj_pos_database.db"
    holder = make_wal_database(legacy, rows=6)
    try:
        holder.execute("BEGIN")
        holder.execute("SELECT COUNT(*) FROM sales").fetchone()
        paths = _installed_paths(tmp_path, legacy=[legacy])
        result = LegacyDatabaseRelocator(paths).run()
        assert result.status is RelocationStatus.FAILED and result.blocks_startup
        assert not paths.database_path.exists()
    finally:
        holder.rollback()
        holder.close()
    assert count_sales(legacy) == 6
    # Once the other program closes, the next start completes the move.
    assert LegacyDatabaseRelocator(_installed_paths(tmp_path, legacy=[legacy])).run().status \
        is RelocationStatus.RELOCATED


def test_media_referenced_by_relative_name_follows_the_database(tmp_path):
    legacy = tmp_path / "old" / "spj_pos_database.db"
    make_wal_database(legacy).close()
    old_root = tmp_path / "roaming"
    (old_root / "media" / "pantalla_cliente").mkdir(parents=True)
    (old_root / "media" / "pantalla_cliente" / "promo.png").write_bytes(b"png")
    paths = _installed_paths(tmp_path, legacy=[legacy])
    LegacyDatabaseRelocator(paths, legacy_data_root=old_root).run()
    assert (paths.display_media_dir / "promo.png").read_bytes() == b"png"
    assert (old_root / "media" / "pantalla_cliente" / "promo.png").exists()  # copied, not moved


def test_installed_paths_follow_the_data_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "PD"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LAD"))
    machine = AppPaths(base_dir=tmp_path / "app", layout=LAYOUT_INSTALLED,
                       install_config=InstallConfig(data_scope="machine"))
    user = AppPaths(base_dir=tmp_path / "app", layout=LAYOUT_INSTALLED,
                    install_config=InstallConfig(data_scope="user"))
    assert machine.database_path == (tmp_path / "PD" / "SPJ" / "SPJ ERP POS" / "db"
                                     / "spj_pos_database.db").resolve()
    assert user.user_data_dir == (tmp_path / "LAD" / "SPJ" / "SPJ ERP POS").resolve()
    assert machine.logs_dir.parent == machine.user_data_dir
    # Rollback installers never live under the user-writable data root.
    assert machine.installer_cache_dir == (tmp_path / "PD" / "SPJ" / "Installers" / "SPJ ERP POS")
    assert user.installer_cache_dir.parent.parent == tmp_path / "PD" / "SPJ"


# ── instance lock ──────────────────────────────────────────────────────────
def test_instance_lock_is_exclusive_within_and_across_processes(tmp_path):
    path = tmp_path / "spj_pos_database.db.lock"
    first, second = InstanceLock(path), InstanceLock(path)
    assert first.acquire()
    assert not second.acquire()
    script = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {str(PACKAGE_ROOT)!r})
        from backend.infrastructure.runtime.instance_lock import InstanceLock
        print(InstanceLock(__import__('pathlib').Path({str(path)!r})).acquire())
    """)
    busy = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          timeout=60)
    assert busy.stdout.strip() == "False", busy.stderr
    first.release()
    free = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          timeout=60)
    assert free.stdout.strip() == "True", free.stderr
    assert second.acquire()
    second.release()
