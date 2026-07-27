"""Updater install skeleton with mandatory SQLite backup support."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil

from backend.infrastructure.updater.update_manifest import UpdateManifest
from backend.shared.app_paths import AppPaths


@dataclass(frozen=True)
class BackupResult:
    source: Path
    destination: Path


@dataclass(frozen=True)
class InstallPlan:
    manifest: UpdateManifest
    package_path: Path
    sqlite_backup: BackupResult | None


class UpdateInstaller:
    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    def backup_sqlite_database(self, database_path: Path | None = None) -> BackupResult | None:
        self._paths.ensure_directories()
        source = database_path or self._paths.sqlite_database_path()
        if not source.exists():
            return None

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = self._paths.backups_dir / f"{source.stem}-{timestamp}{source.suffix}"
        shutil.copy2(source, destination)
        return BackupResult(source=source, destination=destination)

    def plan_install(self, manifest: UpdateManifest, package_path: Path, database_path: Path | None = None) -> InstallPlan:
        backup = self.backup_sqlite_database(database_path)
        return InstallPlan(manifest=manifest, package_path=package_path, sqlite_backup=backup)

    def install(self, manifest: UpdateManifest, package_path: Path, database_path: Path | None = None) -> InstallPlan:
        return self.plan_install(manifest=manifest, package_path=package_path, database_path=database_path)
