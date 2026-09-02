"""ScaleProfilePolicy — is this `DeviceProfile` a legally-shaped scale
profile? (§22). Mirrors printer_profile_policy.py's shape.
"""

from __future__ import annotations

from backend.domain.device_management.enums import SCALE_DEVICE_TYPES, DeviceCapabilityCode, ScaleProtocol
from backend.domain.device_management.exceptions import InvalidScaleProfileError


def assert_valid_scale_profile(profile) -> None:
    if profile.device_type not in SCALE_DEVICE_TYPES:
        raise InvalidScaleProfileError(
            f"{profile.device_type.value} no es un tipo de báscula ({sorted(t.value for t in SCALE_DEVICE_TYPES)})"
        )
    if profile.protocol:
        try:
            ScaleProtocol(profile.protocol)
        except ValueError as exc:
            raise InvalidScaleProfileError(
                f"protocol {profile.protocol!r} no es un protocolo de báscula reconocido "
                f"({[p.value for p in ScaleProtocol]})"
            ) from exc
    if not profile.has_capability(DeviceCapabilityCode.WEIGH):
        raise InvalidScaleProfileError(
            f"{profile.name}: un perfil de báscula debe declarar la capacidad WEIGH"
        )
