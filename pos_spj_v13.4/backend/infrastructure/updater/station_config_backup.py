"""Backup of the station's configuration, next to the database backup.

The SQLite backup holds the queue, the branch anchor, the permissions and the
station row. What lives OUTSIDE the database is `install_config.json` (profile,
channel, update hosts) and `station_settings.json`. An update copies both into
`<backups>/station-config-<label>-<stamp>/` with a `snapshot.json` of hashes.

Secrets are left out on purpose: copying `<data>/secrets` or `whatsapp.env` into
a backups folder would add copies of them. They stay where they are, and neither
updates nor uninstalls touch them.

`restore` writes only to fixed destinations, never to a path read from the
snapshot, and refuses a file whose hash does not match. `install_config.json`
names the hosts updates may come from and the backups folder is writable by every
Windows user, so on a machine-wide installation it is NOT restored: the elevated
installer writes that file again.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

from backend.shared.app_paths import AppPaths
from backend.shared.install_config import INSTALL_CONFIG_FILENAME

SNAPSHOT_FORMAT = "spj-config-snapshot/1"
SNAPSHOT_MANIFEST = "snapshot.json"
STATION_SETTINGS = "station_settings.json"


class ConfigBackupError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StationConfigBackup:
    def __init__(self, paths: AppPaths, *, restore_install_config: bool) -> None:
        self._targets = {INSTALL_CONFIG_FILENAME: paths.root / INSTALL_CONFIG_FILENAME,
                         STATION_SETTINGS: paths.station_settings_path}
        self._restorable = {STATION_SETTINGS}
        if restore_install_config:
            self._restorable.add(INSTALL_CONFIG_FILENAME)

    def create(self, destination_dir: Path, *, label: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        final = Path(destination_dir) / f"station-config-{label}-{stamp}"
        partial = final.with_name(final.name + ".partial")
        partial.mkdir(parents=True)
        try:
            hashes = {}
            for name, source in self._targets.items():
                if source.is_file():
                    shutil.copyfile(source, partial / name)
                    hashes[name] = _sha256(partial / name)
                    if hashes[name] != _sha256(source):
                        raise ConfigBackupError(f"La copia de {name} no coincide con el original.")
            (partial / SNAPSHOT_MANIFEST).write_text(
                json.dumps({"format": SNAPSHOT_FORMAT, "files": hashes}, indent=2),
                encoding="utf-8")
        except Exception:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        os.replace(partial, final)
        return final

    def restore(self, snapshot: Path) -> tuple[str, ...]:
        """Put the snapshot back; returns the names of the files written."""
        snapshot = Path(snapshot)
        try:
            manifest = json.loads((snapshot / SNAPSHOT_MANIFEST).read_text(encoding="utf-8"))
            hashes = manifest["files"]
            pending = {name: hashes[name] for name in self._targets
                       if name in hashes and name in self._restorable}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConfigBackupError(f"El respaldo de configuración no se puede leer: {exc}") from exc
        for name, expected in pending.items():  # all or nothing
            if not (snapshot / name).is_file() or _sha256(snapshot / name) != expected:
                raise ConfigBackupError(f"El respaldo de {name} no coincide con su registro.")
        for name in pending:
            target = self._targets[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".restoring")
            shutil.copyfile(snapshot / name, temporary)
            os.replace(temporary, target)
        return tuple(pending)
