"""Facts about the RUNNING installation, gathered once per process.

Everything the update use cases need to know about "this build on this
machine": version, platform, build metadata, install profile, data paths,
update feed and the hosts packages may come from. Read from `AppPaths`,
`install_config.json` and `build_info.json` — never from the database.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import struct
from pathlib import Path
from urllib.parse import urlsplit

from backend.domain.software_distribution.install_profile import (
    EnabledCapabilities,
    InstallProfile,
)
from backend.domain.software_distribution.release_manifest import TargetPlatform
from backend.domain.software_distribution.semantic_version import SemanticVersion
from backend.shared.app_paths import AppPaths
from backend.shared.app_version import VERSION, BuildMetadata, build_metadata


def current_platform() -> TargetPlatform:
    if struct.calcsize("P") * 8 == 32:
        arch = "x86"
    else:
        machine = platform.machine().lower()
        arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    return TargetPlatform(os="windows", arch=arch)


def enabled_capabilities_for(paths: AppPaths) -> EnabledCapabilities:
    """A source checkout and an installation without profile get everything:
    the profile only narrows what an installer explicitly chose."""
    config = paths.install_config
    if config is None:
        return EnabledCapabilities.everything()
    try:
        profile = InstallProfile(config.profile)
    except ValueError:
        return EnabledCapabilities.everything()
    return EnabledCapabilities.resolve(profile, config.capabilities,
                                       catalog_version=config.capability_catalog)


@dataclass(frozen=True)
class SoftwareInstallation:
    version: SemanticVersion
    platform: TargetPlatform
    build: BuildMetadata
    capabilities: EnabledCapabilities
    paths: AppPaths
    feed_url_template: str
    allowed_hosts: frozenset[str]
    default_channel: str
    whatsapp_mode: str

    @classmethod
    def describe(cls, paths: AppPaths) -> "SoftwareInstallation":
        config = paths.install_config
        feed = config.update_feed_url if config else ""
        hosts = set(config.allowed_update_hosts) if config else set()
        if not paths.is_installed:
            # Development only: an installed station takes these exclusively
            # from install_config.json (written by the elevated installer).
            feed = os.environ.get("SPJ_UPDATE_FEED_URL", feed)
            hosts |= {h.strip().lower() for h in
                      os.environ.get("SPJ_UPDATE_ALLOWED_HOSTS", "").split(",") if h.strip()}
        feed_host = (urlsplit(feed.replace("{channel}", "stable")).hostname or "").lower()
        if feed_host and not hosts:
            hosts.add(feed_host)
        return cls(
            version=SemanticVersion.parse(VERSION),
            platform=current_platform(),
            build=build_metadata(paths.resource_root),
            capabilities=enabled_capabilities_for(paths),
            paths=paths,
            feed_url_template=feed,
            allowed_hosts=frozenset(hosts),
            default_channel=(config.update_channel if config else "stable"),
            whatsapp_mode=(config.whatsapp_mode if config else "remote"),
        )

    def feed_url(self, channel: str) -> str:
        return self.feed_url_template.replace("{channel}", channel)

    @property
    def updater_command(self) -> list[str]:
        """How to start the external updater (see `update_launcher.py`)."""
        root = self.paths.root
        if self.paths.is_installed:
            return [str(root / "spj_updater.exe")]
        import sys
        return [sys.executable, "-m", "backend.infrastructure.updater.updater_main"]

    @property
    def app_command(self) -> list[str]:
        root = self.paths.root
        if self.paths.is_installed:
            return [str(root / "SPJ.exe")]
        import sys
        return [sys.executable, str(Path(root) / "main.py")]
