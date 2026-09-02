"""DeviceIdentifier — a hardware fingerprint (MAC address, USB serial
number, IMEI, ...), not a domain UUID. Kept as its own VO rather than a
bare string so callers can't accidentally pass a UUID or an empty value
where the physical identifier belongs.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.device_management.exceptions import DeviceInvalidValueError


@dataclass(frozen=True, slots=True)
class DeviceIdentifier:
    value: str

    @classmethod
    def create(cls, raw: str) -> "DeviceIdentifier":
        candidate = str(raw or "").strip()
        if not candidate:
            raise DeviceInvalidValueError("El identificador de hardware no puede estar vacío")
        return cls(candidate)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value
