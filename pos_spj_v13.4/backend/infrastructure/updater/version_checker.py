"""Version comparison helpers for the updater skeleton."""

from __future__ import annotations

from dataclasses import dataclass

from backend.infrastructure.updater.update_manifest import UpdateManifest


@dataclass(frozen=True)
class VersionCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    mandatory: bool = False


class VersionChecker:
    def check(self, current_version: str, manifest: UpdateManifest) -> VersionCheckResult:
        return VersionCheckResult(
            current_version=current_version,
            latest_version=manifest.version,
            update_available=_version_tuple(manifest.version) > _version_tuple(current_version),
            mandatory=manifest.mandatory,
        )


def _version_tuple(version: str) -> tuple[int, ...]:
    normalized = version.strip().lstrip("v")
    parts: list[int] = []
    for item in normalized.split("."):
        numeric = "".join(character for character in item if character.isdigit())
        parts.append(int(numeric or "0"))
    return tuple(parts)
