"""Archivos de media de la pantalla del cliente en la carpeta de la aplicación.

Se COPIA el archivo elegido (nunca se guarda la ruta del escritorio de nadie)
y se nombra por el id del registro: `<uuid>.<ext>`.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from backend.shared.app_paths import AppPaths


class DisplayMediaStorage:
    def __init__(self, directory: Path | None = None) -> None:
        self._dir = Path(directory) if directory else AppPaths.from_environment().display_media_dir

    @staticmethod
    def fingerprint(source: Path) -> tuple[int, str]:
        """(tamaño, sha256) sin cargar el archivo completo en memoria."""
        digest = hashlib.sha256()
        with open(source, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return source.stat().st_size, digest.hexdigest()

    def store(self, source: Path, stored_name: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / stored_name
        shutil.copyfile(source, target)
        return target

    def path_for(self, stored_name: str) -> Path:
        return self._dir / stored_name
