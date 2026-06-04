"""Updater download skeleton."""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

from backend.infrastructure.updater.update_manifest import UpdateManifest
from backend.shared.app_paths import AppPaths


class UpdateDownloader:
    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    def target_path(self, manifest: UpdateManifest) -> Path:
        filename = Path(manifest.package_url).name or f"spj-{manifest.version}.update"
        return self._paths.downloads_dir / filename

    def download(self, manifest: UpdateManifest) -> Path:
        self._paths.ensure_directories()
        destination = self.target_path(manifest)
        urlretrieve(manifest.package_url, destination)
        return destination
