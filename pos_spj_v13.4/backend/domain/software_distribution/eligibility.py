"""Decide whether an authenticated release may be offered to THIS station.

Two kinds of "no" are deliberately different:

* REJECTED — the manifest is not acceptable for this station at all (another
  product, channel, platform; a downgrade; a package host outside the
  allow-list; a database schema the release cannot migrate). It is reported
  as an error and never downloaded or executed.
* NOT_OFFERED — the manifest is fine but this station does not take it now
  (already up to date, outside the staged rollout).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib

from backend.domain.software_distribution.release_manifest import (
    PRODUCT_ID,
    ReleaseChannel,
    ReleaseManifest,
    TargetPlatform,
)
from backend.domain.software_distribution.semantic_version import SemanticVersion


class EligibilityOutcome(str, Enum):
    OFFERED = "OFFERED"
    NOT_OFFERED = "NOT_OFFERED"
    REJECTED = "REJECTED"


class EligibilityReason(str, Enum):
    UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
    UP_TO_DATE = "UP_TO_DATE"
    NOT_IN_ROLLOUT = "NOT_IN_ROLLOUT"
    PRODUCT_MISMATCH = "PRODUCT_MISMATCH"
    CHANNEL_MISMATCH = "CHANNEL_MISMATCH"
    PLATFORM_MISMATCH = "PLATFORM_MISMATCH"
    DOWNGRADE_REJECTED = "DOWNGRADE_REJECTED"
    INSTALLED_TOO_OLD = "INSTALLED_TOO_OLD"
    SCHEMA_TOO_OLD = "SCHEMA_TOO_OLD"
    SCHEMA_DOWNGRADE = "SCHEMA_DOWNGRADE"
    HOST_NOT_ALLOWED = "HOST_NOT_ALLOWED"


@dataclass(frozen=True)
class StationIdentity:
    """What the station is running and where it sits in the rollout."""

    installed_version: SemanticVersion
    channel: ReleaseChannel
    platform: TargetPlatform
    database_schema_version: int
    workstation_id: str
    branch_id: str


@dataclass(frozen=True)
class EligibilityDecision:
    outcome: EligibilityOutcome
    reason: EligibilityReason
    message: str

    @property
    def offered(self) -> bool:
        return self.outcome is EligibilityOutcome.OFFERED

    @property
    def rejected(self) -> bool:
        return self.outcome is EligibilityOutcome.REJECTED


def rollout_bucket(version: SemanticVersion, workstation_id: str) -> int:
    """Stable 0..99 bucket per (release, station).

    Including the version means a different subset of stations goes first on
    each release, instead of the same unlucky stations every time.
    """
    digest = hashlib.sha256(f"{version}|{workstation_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


class UpdateEligibilityPolicy:
    def __init__(self, *, allowed_hosts: frozenset[str]) -> None:
        self._allowed_hosts = frozenset(host.lower() for host in allowed_hosts)

    def evaluate(
        self, station: StationIdentity, manifest: ReleaseManifest, *, offline: bool = False,
    ) -> EligibilityDecision:
        """`offline=True` for a package read from removable media: the
        download host and the rollout do not apply, every other rule does."""
        rejected = EligibilityOutcome.REJECTED
        if manifest.product != PRODUCT_ID:
            return _decision(rejected, EligibilityReason.PRODUCT_MISMATCH,
                             f"El paquete es de otro producto ({manifest.product}).")
        if manifest.channel is not station.channel:
            return _decision(
                rejected, EligibilityReason.CHANNEL_MISMATCH,
                f"El paquete es del canal {manifest.channel.label}; esta estación usa "
                f"{station.channel.label}.")
        if manifest.platform != station.platform:
            return _decision(
                rejected, EligibilityReason.PLATFORM_MISMATCH,
                f"El paquete es para {manifest.platform}; esta estación es {station.platform}.")
        if manifest.version < station.installed_version:
            return _decision(
                rejected, EligibilityReason.DOWNGRADE_REJECTED,
                f"La versión {manifest.version} es anterior a la instalada "
                f"({station.installed_version}). No se permite bajar de versión.")
        if manifest.version == station.installed_version:
            return _decision(EligibilityOutcome.NOT_OFFERED, EligibilityReason.UP_TO_DATE,
                             f"Ya tiene la versión {station.installed_version}.")
        minimum = manifest.minimum_installed_version
        if minimum is not None and station.installed_version < minimum:
            return _decision(
                rejected, EligibilityReason.INSTALLED_TOO_OLD,
                f"La versión {manifest.version} requiere tener instalada al menos la {minimum}; "
                "instale primero esa versión intermedia.")
        schema = manifest.database_schema
        if station.database_schema_version < schema.requires_at_least:
            return _decision(
                rejected, EligibilityReason.SCHEMA_TOO_OLD,
                f"La base está en el esquema {station.database_schema_version} y la versión "
                f"{manifest.version} sólo migra desde el {schema.requires_at_least}.")
        if schema.migrates_to < station.database_schema_version:
            return _decision(
                rejected, EligibilityReason.SCHEMA_DOWNGRADE,
                f"La base ya está en el esquema {station.database_schema_version}, más nuevo "
                f"que el de la versión {manifest.version} ({schema.migrates_to}).")
        if not offline and manifest.artifact.host not in self._allowed_hosts:
            return _decision(
                rejected, EligibilityReason.HOST_NOT_ALLOWED,
                f"El servidor {manifest.artifact.host} no está autorizado para descargas.")
        if not offline and not _in_rollout(station, manifest):
            return _decision(
                EligibilityOutcome.NOT_OFFERED, EligibilityReason.NOT_IN_ROLLOUT,
                f"La versión {manifest.version} se está liberando por etapas y aún no "
                "corresponde a esta estación.")
        return _decision(EligibilityOutcome.OFFERED, EligibilityReason.UPDATE_AVAILABLE,
                         f"Versión {manifest.version} disponible.")


def _in_rollout(station: StationIdentity, manifest: ReleaseManifest) -> bool:
    rollout = manifest.rollout
    if station.workstation_id in rollout.workstation_ids:
        return True
    if rollout.branch_ids and station.branch_id not in rollout.branch_ids:
        return False
    return rollout_bucket(manifest.version, station.workstation_id) < rollout.percent


def _decision(outcome, reason, message) -> EligibilityDecision:
    return EligibilityDecision(outcome=outcome, reason=reason, message=message)
