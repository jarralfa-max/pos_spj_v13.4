"""DriverAssignmentPolicy (master prompt §33-34). Never assign by free-text
name — always against a real `DriverOperationalProfile` with capacity.
"""

from __future__ import annotations

from backend.domain.orders_delivery.driver import DriverOperationalProfile
from backend.domain.orders_delivery.exceptions import DriverNotAvailableError


class DriverAssignmentPolicy:
    @staticmethod
    def ensure_can_assign(profile: DriverOperationalProfile) -> None:
        if not profile.active:
            raise DriverNotAvailableError(
                f"El repartidor {profile.driver_id} no está activo")
        if not profile.has_capacity:
            raise DriverNotAvailableError(
                f"El repartidor {profile.driver_id} ya está en su capacidad máxima "
                f"({profile.current_assignment_count}/{profile.capacity})")
