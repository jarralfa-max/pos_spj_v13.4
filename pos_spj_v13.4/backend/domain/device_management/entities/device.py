"""Device — SET-7 (§18): one concrete, registered piece of hardware,
pointing at a reusable `DeviceProfile` for its connection/capability
template.

Status machine — identical shape to
`backend/domain/settings/entities/workstation.py::Workstation` (same
five states, same reasoning): RETIRED is terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.device_management.enums import DeviceStatus
from backend.domain.device_management.exceptions import DeviceInvalidValueError, DeviceTransitionNotAllowedError
from backend.domain.device_management.value_objects.device_identifier import DeviceIdentifier
from backend.shared.ids import new_uuid, validate_uuidv7

_ACTIVATABLE = {DeviceStatus.INACTIVE, DeviceStatus.MAINTENANCE, DeviceStatus.BLOCKED}
_DEACTIVATABLE = {DeviceStatus.ACTIVE, DeviceStatus.MAINTENANCE}
_MAINTENANCE_ENTRY = {DeviceStatus.ACTIVE, DeviceStatus.INACTIVE}
_BLOCKABLE = {DeviceStatus.ACTIVE, DeviceStatus.INACTIVE, DeviceStatus.MAINTENANCE}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Device:
    id: str
    branch_id: str
    profile_id: str
    code: str
    name: str
    hardware_identifier: DeviceIdentifier | None = None
    status: DeviceStatus = DeviceStatus.ACTIVE
    notes: str = ""
    blocked_reason: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, branch_id: str, profile_id: str, code: str, name: str,
        hardware_identifier: DeviceIdentifier | None = None, notes: str = "",
    ) -> "Device":
        validated_branch_id = validate_uuidv7(branch_id)
        validated_profile_id = validate_uuidv7(profile_id)
        if not code.strip():
            raise DeviceInvalidValueError("code es obligatorio")
        if not name.strip():
            raise DeviceInvalidValueError("name es obligatorio")
        return cls(
            id=new_uuid(), branch_id=validated_branch_id, profile_id=validated_profile_id,
            code=code.strip(), name=name.strip(), hardware_identifier=hardware_identifier,
            notes=notes.strip(),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # behavior ------------------------------------------------------------------
    def reassign_profile(self, profile_id: str) -> None:
        self.profile_id = validate_uuidv7(profile_id)
        self._touch()

    def rename(self, name: str) -> None:
        if not name.strip():
            raise DeviceInvalidValueError("name es obligatorio")
        self.name = name.strip()
        self._touch()

    def update_notes(self, notes: str) -> None:
        self.notes = notes.strip()
        self._touch()

    def activate(self) -> None:
        if self.status not in _ACTIVATABLE:
            raise DeviceTransitionNotAllowedError(f"No se puede activar {self.code} desde {self.status.value}")
        self.status = DeviceStatus.ACTIVE
        self.blocked_reason = None
        self._touch()

    def deactivate(self) -> None:
        if self.status not in _DEACTIVATABLE:
            raise DeviceTransitionNotAllowedError(f"No se puede desactivar {self.code} desde {self.status.value}")
        self.status = DeviceStatus.INACTIVE
        self._touch()

    def enter_maintenance(self) -> None:
        if self.status not in _MAINTENANCE_ENTRY:
            raise DeviceTransitionNotAllowedError(
                f"No se puede poner en mantenimiento {self.code} desde {self.status.value}"
            )
        self.status = DeviceStatus.MAINTENANCE
        self._touch()

    def exit_maintenance(self) -> None:
        if self.status is not DeviceStatus.MAINTENANCE:
            raise DeviceTransitionNotAllowedError(f"{self.code} no está en mantenimiento (status={self.status.value})")
        self.status = DeviceStatus.ACTIVE
        self._touch()

    def block(self, reason: str) -> None:
        if self.status not in _BLOCKABLE:
            raise DeviceTransitionNotAllowedError(f"No se puede bloquear {self.code} desde {self.status.value}")
        if not reason.strip():
            raise DeviceInvalidValueError("block() requiere un motivo")
        self.status = DeviceStatus.BLOCKED
        self.blocked_reason = reason.strip()
        self._touch()

    def unblock(self) -> None:
        if self.status is not DeviceStatus.BLOCKED:
            raise DeviceTransitionNotAllowedError(f"{self.code} no está bloqueado (status={self.status.value})")
        self.status = DeviceStatus.ACTIVE
        self.blocked_reason = None
        self._touch()

    def retire(self) -> None:
        if self.status is DeviceStatus.RETIRED:
            raise DeviceTransitionNotAllowedError(f"{self.code} ya está retirado")
        self.status = DeviceStatus.RETIRED
        self._touch()
