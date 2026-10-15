"""Move a pre-installer database into the installed data root — ONCE.

Before the Windows installer existed, the desktop ran from a source folder and
kept its database in `<package>/data/spj_pos_database.db`. An installed
station keeps it in `<data root>/db/spj_pos_database.db` (`AppPaths`). Simply
pointing the application at the new path would start it on an EMPTY database
and show the first-run wizard while the real data sat invisible on disk. This
module is the deliberate migration instead.

Known previous locations (candidates):

* `<installation dir>/data/spj_pos_database.db` (an executable dropped into an
  old source folder);
* every path in `install_config.json` → `legacy_database_paths` (the
  installer asks for the previous folder);
* `SPJ_LEGACY_DB_PATH` (support override).

Decision table, evaluated before the database is opened:

=========================  ==================  =================================
target exists              legacy with data    result
=========================  ==================  =================================
yes                        none                IN_PLACE — normal start
yes                        one or more         CONFLICT — start is blocked
no, relocation marker      —                   MISSING_AFTER_RELOCATION — blocked
no                         more than one       CONFLICT — blocked
no                         exactly one         relocate → RELOCATED (or FAILED)
no                         none                FRESH — first-run wizard
=========================  ==================  =================================

Relocation steps (the application has not opened anything yet):

1. take the target's instance lock (no second desktop on the new path);
2. checkpoint the legacy WAL into the main file and close it (`TRUNCATE`);
3. rename the legacy file to `*.relocating` — on Windows this fails while
   another program has it open, which is exactly the "still in use" check;
4. verified backup of it into `<data>/backups` (label `pre-relocation`);
5. copy with the backup API into `<target>.relocating-tmp`, then integrity
   check, identical row count per table and identical schema version;
6. atomic `os.replace` into the target;
7. write `<data>/db/relocation.json` (the marker);
8. rename the legacy file to `*.relocated-<timestamp>` — kept, never deleted —
   and leave a note beside it.

Any failure in 4–6 removes the temporary copy and renames the legacy file
back: nothing is half-moved and the next start tries again.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3

from backend.infrastructure.db.sqlite_backup import (
    SQLiteBackupService,
    VerifiedBackup,
    database_schema_version,
    has_user_tables,
    table_row_counts,
)
from backend.infrastructure.runtime.instance_lock import InstanceLock
from backend.shared.app_paths import AppPaths

logger = logging.getLogger("spj.db.relocation")

MARKER_FILENAME = "relocation.json"
#: Directories of the data root whose files the database references by a
#: RELATIVE name and that must therefore follow the database. Copied, never
#: moved; existing files are never overwritten.
COMPANION_DIRECTORIES = ("media",)


class RelocationStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    IN_PLACE = "IN_PLACE"
    FRESH = "FRESH"
    RELOCATED = "RELOCATED"
    CONFLICT = "CONFLICT"
    MISSING_AFTER_RELOCATION = "MISSING_AFTER_RELOCATION"
    FAILED = "FAILED"


_BLOCKING = frozenset({
    RelocationStatus.CONFLICT, RelocationStatus.MISSING_AFTER_RELOCATION,
    RelocationStatus.FAILED,
})


@dataclass(frozen=True)
class RelocationResult:
    status: RelocationStatus
    target: Path
    message: str
    source: Path | None = None
    backup: VerifiedBackup | None = None

    @property
    def blocks_startup(self) -> bool:
        return self.status in _BLOCKING


class LegacyDatabaseRelocator:
    def __init__(
        self, paths: AppPaths, *, backup_service: SQLiteBackupService | None = None,
        legacy_data_root: Path | None = None,
    ) -> None:
        self._paths = paths
        self._backups = backup_service or SQLiteBackupService()
        self._legacy_data_root = legacy_data_root

    @property
    def target(self) -> Path:
        return self._paths.database_path

    @property
    def marker_path(self) -> Path:
        return self.target.parent / MARKER_FILENAME

    def candidates(self) -> list[Path]:
        raw: list[Path] = [self._paths.source_database_path]
        config = self._paths.install_config
        if config is not None:
            raw.extend(Path(p) for p in config.legacy_database_paths)
        override = os.environ.get("SPJ_LEGACY_DB_PATH")
        if override:
            raw.append(Path(override))
        target = _normalized(self.target)
        seen: set[str] = set()
        result: list[Path] = []
        for path in raw:
            key = _normalized(path)
            if key == target or key in seen:
                continue
            seen.add(key)
            result.append(Path(path).expanduser())
        return result

    def run(self) -> RelocationResult:
        target = self.target
        if not self._paths.is_installed or os.environ.get("SPJ_DB_PATH"):
            return RelocationResult(RelocationStatus.NOT_APPLICABLE, target,
                                    "Ruta de base fija (código fuente o SPJ_DB_PATH).")
        legacy = [path for path in self.candidates() if has_user_tables(path)]
        if target.exists():
            if legacy:
                return RelocationResult(
                    RelocationStatus.CONFLICT, target,
                    "Hay dos bases de datos: la de esta instalación "
                    f"({target}) y una anterior sin migrar ({legacy[0]}). No se elige "
                    "ninguna en automático. Archive la que no corresponde siguiendo el "
                    "manual de instalación (sección «Dos bases de datos»).",
                    source=legacy[0])
            return RelocationResult(RelocationStatus.IN_PLACE, target, "Base de datos en su lugar.")
        if self.marker_path.exists():
            return RelocationResult(
                RelocationStatus.MISSING_AFTER_RELOCATION, target,
                f"La base de datos ya se había reubicado a {target} y ese archivo no existe. "
                f"No se creará una base vacía. Restaure el respaldo indicado en "
                f"{self.marker_path} o en {self._paths.backups_dir}.")
        if len(legacy) > 1:
            return RelocationResult(
                RelocationStatus.CONFLICT, target,
                "Se encontraron varias bases anteriores: "
                + "; ".join(str(p) for p in legacy)
                + ". Indique cuál conservar (manual de instalación, «Dos bases de datos»).")
        if not legacy:
            return RelocationResult(RelocationStatus.FRESH, target, "Instalación nueva.")
        return self._relocate(legacy[0])

    # ── relocation ────────────────────────────────────────────────────────
    def _relocate(self, legacy: Path) -> RelocationResult:
        target = self.target
        lock = InstanceLock(self._paths.instance_lock_path)
        if not lock.acquire():
            return RelocationResult(RelocationStatus.FAILED, target,
                                    "Otra instancia de SPJ está abierta en esta estación.",
                                    source=legacy)
        try:
            return self._relocate_locked(legacy)
        finally:
            lock.release()

    def _relocate_locked(self, legacy: Path) -> RelocationResult:
        target = self.target
        try:
            _checkpoint(legacy)
        except _InUseError as exc:
            return RelocationResult(RelocationStatus.FAILED, target, str(exc), source=legacy)

        staged = legacy.with_name(legacy.name + ".relocating")
        try:
            os.replace(legacy, staged)
        except OSError as exc:
            return RelocationResult(
                RelocationStatus.FAILED, target,
                f"La base anterior ({legacy}) está en uso por otro programa; ciérrelo e "
                f"intente de nuevo. Detalle: {exc}", source=legacy)

        temporary = target.with_name(target.name + ".relocating-tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = self._backups.create(staged, self._paths.backups_dir,
                                          label="pre-relocation", quiescent=True,
                                          named_after=legacy)
            _copy_and_verify(staged, temporary)
            os.replace(temporary, target)
        except Exception as exc:
            logger.exception("Falló la reubicación de %s", legacy)
            temporary.unlink(missing_ok=True)
            os.replace(staged, legacy)
            return RelocationResult(
                RelocationStatus.FAILED, target,
                f"No se pudo reubicar la base anterior ({legacy}); quedó intacta. "
                f"Detalle: {exc}", source=legacy)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archived = legacy.with_name(f"{legacy.name}.relocated-{stamp}")
        try:
            os.replace(staged, archived)
            archived.with_name(archived.name + ".LEER.txt").write_text(
                "Esta base de datos fue reubicada por el instalador de SPJ.\n"
                f"Fecha (UTC): {stamp}\nNueva ubicación: {target}\n"
                f"Respaldo verificado previo: {backup.path}\n"
                "No la borre hasta confirmar que la estación opera con normalidad.\n",
                encoding="utf-8")
        except OSError:
            logger.warning("La base se reubicó pero no se pudo renombrar %s", staged)
            archived = staged
        companions = self._copy_companions()
        try:
            self.marker_path.write_text(json.dumps({
                "relocated_at": stamp, "from": str(legacy), "archived_as": str(archived),
                "to": str(target), "backup": str(backup.path),
                "schema_version": backup.schema_version,
                "tables": len(backup.row_counts), "companions_copied": companions,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("No se pudo escribir el marcador de reubicación %s", self.marker_path)
        logger.info("Base reubicada de %s a %s (respaldo %s).", legacy, target, backup.path)
        return RelocationResult(
            RelocationStatus.RELOCATED, target,
            f"Se trasladó la base de {legacy} a {target}. Respaldo previo: {backup.path}.",
            source=legacy, backup=backup)

    def _copy_companions(self) -> list[str]:
        source_root = self._legacy_data_root or _source_layout_data_root(self._paths)
        destination_root = self._paths.user_data_dir
        if source_root is None or _normalized(source_root) == _normalized(destination_root):
            return []
        copied: list[str] = []
        for name in COMPANION_DIRECTORIES:
            origin = source_root / name
            if not origin.is_dir():
                continue
            for file in origin.rglob("*"):
                if not file.is_file():
                    continue
                destination = destination_root / name / file.relative_to(origin)
                if destination.exists():
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, destination)  # media files, not SQLite
                copied.append(str(destination.relative_to(destination_root)))
        return copied


class _InUseError(RuntimeError):
    pass


def _checkpoint(path: Path) -> None:
    """Fold the WAL into the main file and close, so the main file alone
    holds every committed transaction before it is renamed."""
    connection = sqlite3.connect(str(path), timeout=2.0)
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        if str(mode).lower() == "wal":
            busy, _, _ = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if busy:
                raise _InUseError(
                    f"La base anterior ({path}) está abierta por otro programa; ciérrelo e "
                    "intente de nuevo.")
    except sqlite3.OperationalError as exc:
        raise _InUseError(f"No se pudo preparar la base anterior ({path}): {exc}") from exc
    finally:
        connection.close()


def _copy_and_verify(source: Path, destination: Path) -> None:
    destination.unlink(missing_ok=True)
    source_conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        expected_counts = table_row_counts(source_conn)
        expected_schema = database_schema_version(source_conn)
        destination_conn = sqlite3.connect(str(destination))
        try:
            source_conn.backup(destination_conn)
            destination_conn.commit()
            check = destination_conn.execute("PRAGMA integrity_check").fetchone()[0]
            if str(check).lower() != "ok":
                raise RuntimeError(f"integrity_check de la copia: {check}")
            if table_row_counts(destination_conn) != expected_counts:
                raise RuntimeError("La copia no tiene las mismas filas que la base anterior.")
            if database_schema_version(destination_conn) != expected_schema:
                raise RuntimeError("La copia no tiene la misma versión de esquema.")
        finally:
            destination_conn.close()
    finally:
        source_conn.close()


def _source_layout_data_root(paths: AppPaths) -> Path | None:
    """Where a source checkout kept product media (`%APPDATA%` on Windows)."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / paths.company_name / paths.app_name


def _normalized(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))
