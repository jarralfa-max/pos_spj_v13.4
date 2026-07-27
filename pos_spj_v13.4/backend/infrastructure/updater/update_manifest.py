"""Update manifest model for desktop updater checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    package_url: str
    checksum_sha256: str
    release_notes: str = ""
    mandatory: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UpdateManifest":
        return cls(
            version=str(payload["version"]),
            package_url=str(payload["package_url"]),
            checksum_sha256=str(payload["checksum_sha256"]),
            release_notes=str(payload.get("release_notes", "")),
            mandatory=bool(payload.get("mandatory", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "package_url": self.package_url,
            "checksum_sha256": self.checksum_sha256,
            "release_notes": self.release_notes,
            "mandatory": self.mandatory,
        }
