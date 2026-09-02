"""Workstation — SET-6 (§17).

Status machine::

    ACTIVE ──deactivate()──► INACTIVE ──activate()──► ACTIVE
      │                          │
      ├──enter_maintenance()──► MAINTENANCE ──exit_maintenance()──► ACTIVE
      │                          │
      ├──block(reason)──► BLOCKED ──unblock()──► ACTIVE
      │                          │
      └──retire()──► RETIRED ◄───┘  (terminal — no transition leaves RETIRED)

`check_in()` is the "Registro"/heartbeat path a live workstation calls
periodically (recording `last_seen_at` and, optionally, its current
`application_version`) — it's a Python-level operation, not a domain
event on its own (a heartbeat every few seconds firing an event is
noise), but is refused once the workstation is BLOCKED or RETIRED.
`is_online()` reads `last_seen_at` against a caller-supplied staleness
threshold — no wall-clock/TTL logic ever guesses that threshold itself
(§53: offline policy is a Settings-governed concern, not hardcoded here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from backend.domain.settings.enums import WorkstationStatus, WorkstationType
from backend.domain.settings.exceptions import (
    ConfigurationInvalidValueError,
    WorkstationTransitionNotAllowedError,
)
from backend.shared.ids import new_uuid, validate_uuidv7

_ACTIVATABLE = {WorkstationStatus.INACTIVE, WorkstationStatus.MAINTENANCE, WorkstationStatus.BLOCKED}
_DEACTIVATABLE = {WorkstationStatus.ACTIVE, WorkstationStatus.MAINTENANCE}
_MAINTENANCE_ENTRY = {WorkstationStatus.ACTIVE, WorkstationStatus.INACTIVE}
_BLOCKABLE = {WorkstationStatus.ACTIVE, WorkstationStatus.INACTIVE, WorkstationStatus.MAINTENANCE}
_CHECK_IN_BLOCKED_FROM = {WorkstationStatus.BLOCKED, WorkstationStatus.RETIRED}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat(timespec="seconds")


@dataclass(slots=True)
class Workstation:
    id: str
    branch_id: str
    code: str
    name: str
    workstation_type: WorkstationType
    device_identifier: str = ""
    operating_system: str = ""
    application_version: str = ""
    status: WorkstationStatus = WorkstationStatus.ACTIVE
    offline_enabled: bool = True
    last_seen_at: str | None = None
    blocked_reason: str | None = None
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, branch_id: str, code: str, name: str, workstation_type: WorkstationType,
        device_identifier: str = "", operating_system: str = "", application_version: str = "",
        offline_enabled: bool = True,
    ) -> "Workstation":
        validated_branch_id = validate_uuidv7(branch_id)
        if not code.strip():
            raise ConfigurationInvalidValueError("code es obligatorio")
        if not name.strip():
            raise ConfigurationInvalidValueError("name es obligatorio")
        return cls(
            id=new_uuid(), branch_id=validated_branch_id, code=code.strip(), name=name.strip(),
            workstation_type=workstation_type, device_identifier=device_identifier.strip(),
            operating_system=operating_system.strip(), application_version=application_version.strip(),
            offline_enabled=bool(offline_enabled),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow_iso()

    # registro / versión / offline ---------------------------------------------
    def check_in(self, *, application_version: str | None = None, at: datetime | None = None) -> None:
        if self.status in _CHECK_IN_BLOCKED_FROM:
            raise WorkstationTransitionNotAllowedError(
                f"La estación {self.code} no puede registrar actividad desde {self.status.value}"
            )
        self.last_seen_at = (at or _utcnow()).isoformat(timespec="seconds")
        if application_version:
            self.application_version = application_version.strip()
        self._touch()

    def is_online(self, *, at: datetime, staleness_threshold: timedelta) -> bool:
        if self.last_seen_at is None:
            return False
        last_seen = datetime.fromisoformat(self.last_seen_at)
        return (at - last_seen) <= staleness_threshold

    def set_offline_enabled(self, enabled: bool) -> None:
        self.offline_enabled = bool(enabled)
        self._touch()

    def update_details(
        self, *, name: str, device_identifier: str = "", operating_system: str = "",
    ) -> None:
        if not name.strip():
            raise ConfigurationInvalidValueError("name es obligatorio")
        self.name = name.strip()
        self.device_identifier = device_identifier.strip()
        self.operating_system = operating_system.strip()
        self._touch()

    # estado ----------------------------------------------------------------
    def activate(self) -> None:
        if self.status not in _ACTIVATABLE:
            raise WorkstationTransitionNotAllowedError(
                f"No se puede activar la estación {self.code} desde {self.status.value}"
            )
        self.status = WorkstationStatus.ACTIVE
        self.blocked_reason = None
        self._touch()

    def deactivate(self) -> None:
        if self.status not in _DEACTIVATABLE:
            raise WorkstationTransitionNotAllowedError(
                f"No se puede desactivar la estación {self.code} desde {self.status.value}"
            )
        self.status = WorkstationStatus.INACTIVE
        self._touch()

    def enter_maintenance(self) -> None:
        if self.status not in _MAINTENANCE_ENTRY:
            raise WorkstationTransitionNotAllowedError(
                f"No se puede poner en mantenimiento la estación {self.code} desde {self.status.value}"
            )
        self.status = WorkstationStatus.MAINTENANCE
        self._touch()

    def exit_maintenance(self) -> None:
        if self.status is not WorkstationStatus.MAINTENANCE:
            raise WorkstationTransitionNotAllowedError(
                f"La estación {self.code} no está en mantenimiento (status={self.status.value})"
            )
        self.status = WorkstationStatus.ACTIVE
        self._touch()

    def block(self, reason: str) -> None:
        if self.status not in _BLOCKABLE:
            raise WorkstationTransitionNotAllowedError(
                f"No se puede bloquear la estación {self.code} desde {self.status.value}"
            )
        if not reason.strip():
            raise ConfigurationInvalidValueError("block() requiere un motivo")
        self.status = WorkstationStatus.BLOCKED
        self.blocked_reason = reason.strip()
        self._touch()

    def unblock(self) -> None:
        if self.status is not WorkstationStatus.BLOCKED:
            raise WorkstationTransitionNotAllowedError(
                f"La estación {self.code} no está bloqueada (status={self.status.value})"
            )
        self.status = WorkstationStatus.ACTIVE
        self.blocked_reason = None
        self._touch()

    def retire(self) -> None:
        if self.status is WorkstationStatus.RETIRED:
            raise WorkstationTransitionNotAllowedError(f"La estación {self.code} ya está retirada")
        self.status = WorkstationStatus.RETIRED
        self._touch()
