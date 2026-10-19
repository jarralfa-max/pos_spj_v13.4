"""Station install configuration — `install_config.json` next to the executable.

The Windows installer writes this file into the installation directory
(`Program Files`, read-only for normal users) from the choices made in the
wizard: where the data lives, which install profile, which update channel the
station starts on, where to look for updates, and where a previous
(pre-installer) database may be. Nothing here is secret.

A source checkout has no such file: `InstallConfig.load()` returns `None` and
`AppPaths` keeps the development layout (`<package>/data`, `<package>/logs`).

Format `spj-install/1`:

    {
      "format": "spj-install/1",
      "data_scope": "machine" | "user",
      "profile": "pos_essential" | "erp_full" | "custom",
      "capabilities": ["sales_pos", ...],          # used by "custom" only
      "update_channel": "stable" | "pilot",
      "update_feed_url": "https://updates.example/spj/{channel}/manifest.json",
      "allowed_update_hosts": ["updates.example"],
      "legacy_database_paths": ["C:\\\\SPJ\\\\pos_spj_v13.4\\\\data\\\\spj_pos_database.db"],
      "whatsapp_mode": "remote" | "local",
      "install_mode": "admin" | "user",         # user = /CURRENTUSER, no UAC
      "capability_catalog": 2                    # falta = 1 (antes de `logistics`)
    }

Pure stdlib on purpose: `AppPaths` (this same `shared` layer) needs the data
scope before anything else exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

INSTALL_CONFIG_FILENAME = "install_config.json"
INSTALL_CONFIG_FORMAT = "spj-install/1"

DATA_SCOPE_MACHINE = "machine"
DATA_SCOPE_USER = "user"


class InstallConfigError(ValueError):
    """`install_config.json` exists but cannot be trusted. Starting anyway with
    defaults could point the application at an empty database, so callers
    stop with a diagnostic instead."""


@dataclass(frozen=True)
class InstallConfig:
    data_scope: str = DATA_SCOPE_USER
    profile: str = "erp_full"
    capabilities: tuple[str, ...] = ()
    update_channel: str = "stable"
    update_feed_url: str = ""
    allowed_update_hosts: tuple[str, ...] = ()
    legacy_database_paths: tuple[str, ...] = ()
    whatsapp_mode: str = "remote"
    #: "admin": installed for the machine (Program Files, UAC to update).
    #: "user": installed with /CURRENTUSER for one Windows user, no elevation.
    install_mode: str = "admin"
    #: Versión del catálogo de capacidades con que se escribió (1 si falta: un
    #: instalador anterior a la capacidad `logistics`).
    capability_catalog: int = 1
    source_file: Path | None = field(default=None, compare=False)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, source_file: Path | None = None) -> "InstallConfig":
        if data.get("format") != INSTALL_CONFIG_FORMAT:
            raise InstallConfigError(
                f"Formato de install_config.json no soportado: {data.get('format')!r}")
        scope = str(data.get("data_scope") or DATA_SCOPE_USER).lower()
        if scope not in {DATA_SCOPE_MACHINE, DATA_SCOPE_USER}:
            raise InstallConfigError(f"data_scope inválido: {scope!r}")
        whatsapp_mode = str(data.get("whatsapp_mode") or "remote").lower()
        if whatsapp_mode not in {"remote", "local"}:
            raise InstallConfigError(f"whatsapp_mode inválido: {whatsapp_mode!r}")
        install_mode = str(data.get("install_mode") or "admin").lower()
        if install_mode not in {"admin", "user"}:
            raise InstallConfigError(f"install_mode inválido: {install_mode!r}")
        try:
            catalog = int(data.get("capability_catalog") or 1)
        except (TypeError, ValueError) as exc:
            raise InstallConfigError("capability_catalog inválido") from exc
        return cls(
            capability_catalog=catalog,
            install_mode=install_mode,
            data_scope=scope,
            profile=str(data.get("profile") or "erp_full").lower(),
            capabilities=tuple(str(c) for c in data.get("capabilities") or ()),
            update_channel=str(data.get("update_channel") or "stable").lower(),
            update_feed_url=str(data.get("update_feed_url") or ""),
            allowed_update_hosts=tuple(
                str(h).lower() for h in data.get("allowed_update_hosts") or ()),
            legacy_database_paths=tuple(str(p) for p in data.get("legacy_database_paths") or ()),
            whatsapp_mode=whatsapp_mode,
            source_file=source_file,
        )

    @classmethod
    def load(cls, install_dir: Path) -> "InstallConfig | None":
        path = Path(install_dir) / INSTALL_CONFIG_FILENAME
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise InstallConfigError(f"No se pudo leer {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise InstallConfigError(f"{path} no contiene un objeto JSON.")
        return cls.from_mapping(data, source_file=path)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "format": INSTALL_CONFIG_FORMAT,
            "data_scope": self.data_scope,
            "profile": self.profile,
            "capabilities": list(self.capabilities),
            "update_channel": self.update_channel,
            "update_feed_url": self.update_feed_url,
            "allowed_update_hosts": list(self.allowed_update_hosts),
            "legacy_database_paths": list(self.legacy_database_paths),
            "whatsapp_mode": self.whatsapp_mode,
            "install_mode": self.install_mode,
        }
