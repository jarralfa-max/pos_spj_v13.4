"""CashDrawerProfilePolicy — is this `DeviceProfile` a legally-shaped
cash-drawer profile? (§18/§20/§23). Mirrors printer/scale profile
policies' shape.
"""

from __future__ import annotations

from backend.domain.device_management.enums import CASH_DRAWER_DEVICE_TYPES, DeviceCapabilityCode
from backend.domain.device_management.exceptions import InvalidCashDrawerProfileError


def assert_valid_cash_drawer_profile(profile) -> None:
    if profile.device_type not in CASH_DRAWER_DEVICE_TYPES:
        raise InvalidCashDrawerProfileError(
            f"{profile.device_type.value} no es un tipo de cajón "
            f"({sorted(t.value for t in CASH_DRAWER_DEVICE_TYPES)})"
        )
    if not profile.has_capability(DeviceCapabilityCode.DRAWER_PULSE):
        raise InvalidCashDrawerProfileError(
            f"{profile.name}: un perfil de cajón debe declarar la capacidad DRAWER_PULSE"
        )
