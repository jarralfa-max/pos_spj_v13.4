"""DeviceAssignmentPolicy — is this device type legal for this role?
(§20). Role/device_type compatibility is checked here; the "no two
active devices in the same role at one workstation" rule is a schema
constraint (SET-7 infra) plus, at the repository/use-case layer, a check
of `list_active_for_role` before assigning — this policy only knows
about role↔type legality, nothing about what's already assigned.
"""

from __future__ import annotations

from backend.domain.device_management.enums import ROLE_COMPATIBLE_DEVICE_TYPES, AssignmentRole, DeviceType
from backend.domain.device_management.exceptions import DeviceAssignmentRoleNotCompatibleError


def compatible_device_types(role: AssignmentRole) -> frozenset[DeviceType]:
    return ROLE_COMPATIBLE_DEVICE_TYPES[role]


def assert_role_compatible_with_device_type(role: AssignmentRole, device_type: DeviceType) -> None:
    allowed = compatible_device_types(role)
    if device_type not in allowed:
        raise DeviceAssignmentRoleNotCompatibleError(
            f"El rol {role.value} requiere un dispositivo de tipo "
            f"{sorted(t.value for t in allowed)}, no {device_type.value}"
        )
