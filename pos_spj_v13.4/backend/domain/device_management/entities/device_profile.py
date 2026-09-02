"""DeviceProfile — SET-7 (§19): the reusable connection/capability
template a `Device` instance points at (e.g. "Epson TM-T20III USB
80mm"). Multiple physical devices of the same model share one profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.device_management.enums import DeviceType
from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.device_capability import DeviceCapability
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DeviceProfile:
    id: str
    name: str
    device_type: DeviceType
    connection_profile: ConnectionProfile
    manufacturer: str = ""
    model: str = ""
    capabilities: tuple[DeviceCapability, ...] = ()
    paper_profile: str | None = None
    protocol: str = ""
    driver_name: str = ""
    timeout_seconds: int = 5
    retry_max_attempts: int = 3
    health_check_enabled: bool = True
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, name: str, device_type: DeviceType, connection_profile: ConnectionProfile,
        manufacturer: str = "", model: str = "", capabilities: tuple[DeviceCapability, ...] = (),
        paper_profile: str | None = None, protocol: str = "", driver_name: str = "",
        timeout_seconds: int = 5, retry_max_attempts: int = 3, health_check_enabled: bool = True,
    ) -> "DeviceProfile":
        if not name.strip():
            raise DeviceInvalidValueError("name es obligatorio")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise DeviceInvalidValueError(f"timeout_seconds debe ser un entero positivo, recibido {timeout_seconds!r}")
        if isinstance(retry_max_attempts, bool) or not isinstance(retry_max_attempts, int) or retry_max_attempts < 0:
            raise DeviceInvalidValueError(
                f"retry_max_attempts debe ser un entero >= 0, recibido {retry_max_attempts!r}"
            )
        return cls(
            id=new_uuid(), name=name.strip(), device_type=device_type, connection_profile=connection_profile,
            manufacturer=manufacturer.strip(), model=model.strip(), capabilities=tuple(capabilities),
            paper_profile=paper_profile.strip() if paper_profile else None, protocol=protocol.strip(),
            driver_name=driver_name.strip(), timeout_seconds=timeout_seconds,
            retry_max_attempts=retry_max_attempts, health_check_enabled=bool(health_check_enabled),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # behavior ------------------------------------------------------------------
    def has_capability(self, code) -> bool:
        return any(capability.code == code for capability in self.capabilities)

    def add_capability(self, capability: DeviceCapability) -> None:
        if self.has_capability(capability.code):
            raise DeviceInvalidValueError(f"{self.name} ya declara la capacidad {capability.code.value}")
        self.capabilities = (*self.capabilities, capability)
        self._touch()

    def remove_capability(self, code) -> None:
        if not self.has_capability(code):
            raise DeviceInvalidValueError(f"{self.name} no declara la capacidad {code.value}")
        self.capabilities = tuple(c for c in self.capabilities if c.code != code)
        self._touch()

    def replace_connection_profile(self, connection_profile: ConnectionProfile) -> None:
        self.connection_profile = connection_profile
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
