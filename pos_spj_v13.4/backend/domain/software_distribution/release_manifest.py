"""Release manifest — the authenticated description of one published build.

The manifest is only trusted AFTER its signature is verified by the updater
infrastructure (`backend/infrastructure/updater/update_manifest.py`). This
module validates the *shape and semantics* of the already-authenticated
payload: a signed manifest with an impossible value (negative size, a hash
that is not SHA-256, plain-HTTP URL) is still rejected here.

Payload format `spj-release/1`:

    {
      "format": "spj-release/1",
      "product": "spj-erp-pos",
      "version": "13.5.0",
      "channel": "stable",
      "published_at": "2026-10-14T00:00:00Z",
      "platform": {"os": "windows", "arch": "x64"},
      "minimum_installed_version": "13.4.0",
      "database_schema": {"requires_at_least": 300, "migrates_to": 340},
      "artifact": {"kind": "inno-setup", "file_name": "SPJ-Setup-13.5.0-x64.exe",
                   "url": "https://.../SPJ-Setup-13.5.0-x64.exe",
                   "size": 123456789, "sha256": "<64 hex>"},
      "release_notes": "…",
      "mandatory": false,
      "mandatory_deadline": null,
      "rollout": {"percent": 100, "branch_ids": [], "workstation_ids": []}
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import PurePosixPath
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from backend.domain.software_distribution.semantic_version import (
    InvalidVersionError,
    SemanticVersion,
)

MANIFEST_FORMAT = "spj-release/1"
PRODUCT_ID = "spj-erp-pos"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ManifestValidationError(ValueError):
    """The (authenticated) manifest payload is malformed or inconsistent."""


class ReleaseChannel(str, Enum):
    STABLE = "stable"
    PILOT = "pilot"

    @classmethod
    def parse(cls, value: str) -> "ReleaseChannel":
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            raise ManifestValidationError(
                f"Canal desconocido: {value!r} (válidos: stable, pilot)") from exc

    @property
    def label(self) -> str:
        return {"stable": "Estable", "pilot": "Piloto"}[self.value]


class ArtifactKind(str, Enum):
    INNO_SETUP = "inno-setup"


@dataclass(frozen=True)
class TargetPlatform:
    os: str
    arch: str

    def __post_init__(self) -> None:
        if self.os not in {"windows"}:
            raise ManifestValidationError(f"Sistema operativo no soportado: {self.os!r}")
        if self.arch not in {"x64", "x86", "arm64"}:
            raise ManifestValidationError(f"Arquitectura no soportada: {self.arch!r}")

    def __str__(self) -> str:
        return f"{self.os}-{self.arch}"


@dataclass(frozen=True)
class SchemaRange:
    """`requires_at_least`: oldest database schema the release can migrate
    from. `migrates_to`: schema the release leaves the database at."""

    requires_at_least: int
    migrates_to: int

    def __post_init__(self) -> None:
        if self.requires_at_least < 0 or self.migrates_to < 0:
            raise ManifestValidationError("Las versiones de esquema no pueden ser negativas.")
        if self.migrates_to < self.requires_at_least:
            raise ManifestValidationError(
                "El esquema destino es menor que el mínimo requerido.")


@dataclass(frozen=True)
class ReleaseArtifact:
    kind: ArtifactKind
    file_name: str
    url: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not _FILE_NAME.match(self.file_name) or self.file_name in {".", ".."}:
            raise ManifestValidationError(f"Nombre de archivo inválido: {self.file_name!r}")
        if not self.file_name.lower().endswith(".exe"):
            raise ManifestValidationError("El paquete debe ser un instalador .exe.")
        if self.size <= 0:
            raise ManifestValidationError("El tamaño del paquete debe ser positivo.")
        if not _SHA256.match(self.sha256):
            raise ManifestValidationError("El hash debe ser SHA-256 en hexadecimal minúsculo.")
        parts = urlsplit(self.url)
        if parts.scheme != "https" or not parts.hostname:
            raise ManifestValidationError("La URL del paquete debe ser HTTPS.")
        if parts.username or parts.password:
            raise ManifestValidationError("La URL del paquete no puede llevar credenciales.")
        if PurePosixPath(parts.path).name != self.file_name:
            raise ManifestValidationError(
                "El nombre del archivo no coincide con la URL del paquete.")

    @property
    def host(self) -> str:
        return (urlsplit(self.url).hostname or "").lower()


@dataclass(frozen=True)
class RolloutPolicy:
    percent: int = 100
    branch_ids: frozenset[str] = field(default_factory=frozenset)
    workstation_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not 0 <= self.percent <= 100:
            raise ManifestValidationError("El porcentaje de despliegue debe estar entre 0 y 100.")


@dataclass(frozen=True)
class ReleaseManifest:
    product: str
    version: SemanticVersion
    channel: ReleaseChannel
    published_at: datetime
    platform: TargetPlatform
    minimum_installed_version: SemanticVersion | None
    database_schema: SchemaRange
    artifact: ReleaseArtifact
    release_notes: str = ""
    mandatory: bool = False
    mandatory_deadline: date | None = None
    rollout: RolloutPolicy = field(default_factory=RolloutPolicy)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ReleaseManifest":
        if not isinstance(payload, Mapping):
            raise ManifestValidationError("El manifiesto debe ser un objeto JSON.")
        if payload.get("format") != MANIFEST_FORMAT:
            raise ManifestValidationError(
                f"Formato de manifiesto no soportado: {payload.get('format')!r}")
        try:
            platform = payload["platform"]
            schema = payload["database_schema"]
            artifact = payload["artifact"]
            rollout = payload.get("rollout") or {}
            minimum = payload.get("minimum_installed_version")
            deadline = payload.get("mandatory_deadline")
            return cls(
                product=_text(payload["product"]),
                version=SemanticVersion.parse(payload["version"]),
                channel=ReleaseChannel.parse(payload["channel"]),
                published_at=_timestamp(payload["published_at"]),
                platform=TargetPlatform(os=_text(platform["os"]), arch=_text(platform["arch"])),
                minimum_installed_version=SemanticVersion.parse(minimum) if minimum else None,
                database_schema=SchemaRange(
                    requires_at_least=_integer(schema["requires_at_least"]),
                    migrates_to=_integer(schema["migrates_to"]),
                ),
                artifact=ReleaseArtifact(
                    kind=ArtifactKind(_text(artifact["kind"])),
                    file_name=_text(artifact["file_name"]),
                    url=_text(artifact["url"]),
                    size=_integer(artifact["size"]),
                    sha256=_text(artifact["sha256"]),
                ),
                release_notes=str(payload.get("release_notes") or ""),
                mandatory=_boolean(payload.get("mandatory", False)),
                mandatory_deadline=date.fromisoformat(deadline) if deadline else None,
                rollout=RolloutPolicy(
                    percent=_integer(rollout.get("percent", 100)),
                    branch_ids=frozenset(_text(v) for v in rollout.get("branch_ids") or ()),
                    workstation_ids=frozenset(
                        _text(v) for v in rollout.get("workstation_ids") or ()),
                ),
            )
        except ManifestValidationError:
            raise
        except InvalidVersionError as exc:
            raise ManifestValidationError(str(exc)) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestValidationError(f"Manifiesto incompleto o inválido: {exc}") from exc

    def to_payload(self) -> dict[str, Any]:
        """Inverse of `from_payload` — used by the release tooling."""
        return {
            "format": MANIFEST_FORMAT,
            "product": self.product,
            "version": str(self.version),
            "channel": self.channel.value,
            "published_at": self.published_at.isoformat().replace("+00:00", "Z"),
            "platform": {"os": self.platform.os, "arch": self.platform.arch},
            "minimum_installed_version": (
                str(self.minimum_installed_version) if self.minimum_installed_version else None),
            "database_schema": {
                "requires_at_least": self.database_schema.requires_at_least,
                "migrates_to": self.database_schema.migrates_to,
            },
            "artifact": {
                "kind": self.artifact.kind.value,
                "file_name": self.artifact.file_name,
                "url": self.artifact.url,
                "size": self.artifact.size,
                "sha256": self.artifact.sha256,
            },
            "release_notes": self.release_notes,
            "mandatory": self.mandatory,
            "mandatory_deadline": (
                self.mandatory_deadline.isoformat() if self.mandatory_deadline else None),
            "rollout": {
                "percent": self.rollout.percent,
                "branch_ids": sorted(self.rollout.branch_ids),
                "workstation_ids": sorted(self.rollout.workstation_ids),
            },
        }


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"Se esperaba texto no vacío, llegó {value!r}")
    return value.strip()


def _integer(value: Any) -> int:
    # `bool` is an `int` subclass: `true` must not be accepted as a size.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestValidationError(f"Se esperaba un entero, llegó {value!r}")
    return value


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ManifestValidationError(f"Se esperaba verdadero/falso, llegó {value!r}")
    return value


def _timestamp(value: Any) -> datetime:
    text = _text(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestValidationError(f"Fecha de publicación inválida: {text!r}") from exc
    if parsed.tzinfo is None:
        raise ManifestValidationError("La fecha de publicación debe incluir zona horaria.")
    return parsed
