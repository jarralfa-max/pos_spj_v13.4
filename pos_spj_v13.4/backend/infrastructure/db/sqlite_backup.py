"""Consistent, verified SQLite backups — the only way the updater and the
legacy relocation copy the operational database.

Never `shutil.copy2` a live SQLite file: in WAL mode the committed data may be
in `-wal`, not in the main file, and a byte copy taken while another
connection writes can be torn. This module uses the SQLite Online Backup API
(https://sqlite.org/backup.html) through `sqlite3.Connection.backup`, copying
all pages in ONE step so the copy is a single consistent snapshot, then
verifies the copy before declaring it a backup:

* `PRAGMA integrity_check` returns `ok`;
* when the source is quiescent (the caller holds the instance lock), every
  table has the same row count as the source;
* size, SHA-256 and the database schema version are recorded in a JSON
  sidecar (`<backup>.json`) so a person can inspect it without opening it.

The copy is written to `<name>.partial` and renamed only after verification:
a half-written file never carries the final backup name.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3


class BackupVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedBackup:
    path: Path
    source: Path
    label: str
    created_at: str
    size: int
    sha256: str
    schema_version: int | None
    row_counts: dict[str, int] = field(default_factory=dict)
    app_version: str = ""

    @property
    def metadata_path(self) -> Path:
        return self.path.with_name(self.path.name + ".json")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["path"] = str(self.path)
        data["source"] = str(self.source)
        return data


def database_schema_version(connection: sqlite3.Connection) -> int | None:
    """Highest applied migration, or None for a database never migrated."""
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if exists is None:
        return None
    from backend.shared.schema_versions import station_schema_version

    return station_schema_version(
        row[0] for row in connection.execute("SELECT version FROM schema_migrations"))


def table_row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]
    return {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in names}


def checkpoint_wal(connection) -> bool:
    """Fold the WAL into the main file before handing the database to another
    process (the external updater). True when nothing was left pending."""
    try:
        row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except sqlite3.Error:
        return False
    return bool(row) and not row[0]


def has_user_tables(path: Path) -> bool:
    """True when the file is an SQLite database with at least one table."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        # Unreadable is NOT "empty": treat it as data so nobody starts over it.
        return True
    return bool(row and row[0])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "unknown"


class SQLiteBackupService:
    def __init__(self, *, app_version: str = "") -> None:
        self._app_version = app_version

    def create(
        self, source: Path, destination_dir: Path, *, label: str, quiescent: bool = True,
        named_after: Path | None = None,
    ) -> VerifiedBackup:
        """Back up `source` into `destination_dir` and verify the copy.

        `quiescent=True` (the caller holds the instance lock, nobody writes)
        additionally compares every table's row count with the source.
        `named_after` names the backup after another path (the relocation backs
        up a temporarily renamed file but the backup must carry the real name).
        """
        source = Path(source)
        if not source.is_file():
            raise BackupVerificationError(f"No existe la base a respaldar: {source}")
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        name = Path(named_after) if named_after is not None else source
        final = destination_dir / f"{name.stem}-{label}-{stamp}{name.suffix or '.db'}"
        partial = final.with_name(final.name + ".partial")

        source_conn = sqlite3.connect(str(source))
        try:
            destination_conn = sqlite3.connect(str(partial))
            try:
                source_conn.backup(destination_conn)  # all pages, one snapshot
                destination_conn.commit()
                # A backup is an archive, not a live database: rollback-journal
                # mode means it is ONE self-contained file (no -wal/-shm) that
                # can be opened read-only anywhere.
                destination_conn.execute("PRAGMA journal_mode=DELETE")
            finally:
                destination_conn.close()
            source_counts = table_row_counts(source_conn) if quiescent else None
        finally:
            source_conn.close()

        try:
            backup = self._verify_file(partial, source=source, label=label,
                                       expected_counts=source_counts)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        os.replace(partial, final)
        backup = VerifiedBackup(**{**backup.__dict__, "path": final})
        backup.metadata_path.write_text(
            json.dumps(backup.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return backup

    def verify(self, backup_path: Path) -> VerifiedBackup:
        """Re-verify an existing backup (integrity + hash against its sidecar)."""
        backup_path = Path(backup_path)
        sidecar = backup_path.with_name(backup_path.name + ".json")
        recorded = {}
        if sidecar.exists():
            recorded = json.loads(sidecar.read_text(encoding="utf-8"))
        backup = self._verify_file(
            backup_path, source=Path(recorded.get("source", backup_path)),
            label=str(recorded.get("label", "")), expected_counts=None)
        if recorded.get("sha256") and recorded["sha256"] != backup.sha256:
            raise BackupVerificationError(
                f"El respaldo {backup_path.name} no coincide con su registro (hash distinto).")
        return backup

    def restore(self, backup_path: Path, target: Path) -> VerifiedBackup:
        """Restore a verified backup over `target`. Caller holds the instance
        lock: nobody else has `target` open.

        Restores through the backup API INTO the target connection, so its
        WAL is handled by SQLite. If the target cannot even be opened, it is
        moved aside (never deleted) together with its -wal/-shm and the
        backup is written to a fresh file.
        """
        backup = self.verify(backup_path)
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._copy_into(backup.path, target)
        except sqlite3.DatabaseError:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            for suffix in ("", "-wal", "-shm"):
                damaged = target.with_name(target.name + suffix)
                if damaged.exists():
                    os.replace(damaged, damaged.with_name(damaged.name + f".damaged-{stamp}"))
            self._copy_into(backup.path, target)
        check = sqlite3.connect(str(target))
        try:
            result = _integrity(check)
        finally:
            check.close()
        if result.lower() != "ok":
            raise BackupVerificationError(f"La base restaurada no pasó integrity_check: {result}")
        return backup

    @staticmethod
    def _copy_into(source: Path, target: Path) -> None:
        source_conn = sqlite3.connect(f"file:{Path(source).as_posix()}?mode=ro", uri=True)
        try:
            target_conn = sqlite3.connect(str(target))
            try:
                source_conn.backup(target_conn)
                target_conn.commit()
            finally:
                target_conn.close()
        finally:
            source_conn.close()

    def _verify_file(
        self, path: Path, *, source: Path, label: str, expected_counts: dict[str, int] | None,
    ) -> VerifiedBackup:
        connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
        try:
            result = _integrity(connection)
            if result.lower() != "ok":
                raise BackupVerificationError(f"El respaldo no pasó integrity_check: {result}")
            counts = table_row_counts(connection)
            schema_version = database_schema_version(connection)
        finally:
            connection.close()
        if expected_counts is not None and counts != expected_counts:
            differing = sorted(
                name for name in set(counts) | set(expected_counts)
                if counts.get(name) != expected_counts.get(name))
            raise BackupVerificationError(
                "El respaldo no coincide con la base original en: " + ", ".join(differing[:10]))
        return VerifiedBackup(
            path=Path(path), source=Path(source), label=label,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            size=Path(path).stat().st_size, sha256=_sha256(Path(path)),
            schema_version=schema_version, row_counts=counts, app_version=self._app_version,
        )
