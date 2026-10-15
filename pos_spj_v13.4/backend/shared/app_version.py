"""Identidad y versión de la aplicación — ÚNICA fuente.

`VERSION` es el único lugar donde se edita la versión a mano. Todo lo demás la
deriva de aquí: la ventana y el diálogo «Acerca de», el `.spec` de PyInstaller
y el recurso de versión del `.exe`, el instalador Inno Setup
(`scripts/release/build_windows_release.py` la lee con `ast`, sin importar la
aplicación), el manifiesto de la versión y la tabla `software_station_versions`.

El antiguo `version.py` de la raíz se retiró el 2026-10-14 (no tenía ningún
consumidor).

Los metadatos de compilación (commit, fecha, número de build) NO se escriben a
mano: el script de release genera `build_info.json` y lo empaqueta junto a los
recursos; desde el código fuente no existe y `build_metadata()` lo dice.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

APP_NAME = "SPJ POS Enterprise"
PUBLISHER = "SPJ"
#: Versión semántica (https://semver.org). Pre-release con guion: "13.5.0-rc.1".
VERSION = "13.4.0"

BUILD_INFO_FILENAME = "build_info.json"


@dataclass(frozen=True)
class BuildMetadata:
    version: str
    commit: str
    built_at: str
    build_number: str
    signed: bool
    source_checkout: bool

    @property
    def label(self) -> str:
        if self.source_checkout:
            return f"{self.version} (código fuente)"
        return f"{self.version} (build {self.build_number}, {self.commit[:10]})"


def build_metadata(resource_root: Path) -> BuildMetadata:
    """Lee `build_info.json` del paquete; desde el código fuente no existe."""
    path = Path(resource_root) / BUILD_INFO_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return BuildMetadata(version=VERSION, commit="", built_at="", build_number="",
                             signed=False, source_checkout=True)
    return BuildMetadata(
        version=str(data.get("version") or VERSION),
        commit=str(data.get("commit") or ""),
        built_at=str(data.get("built_at") or ""),
        build_number=str(data.get("build_number") or ""),
        signed=bool(data.get("signed", False)),
        source_checkout=False,
    )
