"""DeviceCapability — one thing a `DeviceProfile` can do, optionally
parameterized (e.g. `WEIGH` with `{"max_weight_kg": "30"}`). See §23.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.device_management.enums import DeviceCapabilityCode


@dataclass(frozen=True, slots=True)
class DeviceCapability:
    code: DeviceCapabilityCode
    parameters: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(cls, code: DeviceCapabilityCode, parameters: dict[str, str] | None = None) -> "DeviceCapability":
        return cls(code, dict(parameters or {}))
