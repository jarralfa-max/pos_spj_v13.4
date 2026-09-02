"""Use cases for the "Asignaciones" action on the Estaciones (General)
section — SET-7's fourth pillar (Devices/Profiles/Capabilities/
**Assignments**) had zero UI before this round; the other three were
closed by the Dispositivos round. Thin orchestration only —
`WorkstationDeviceAssignment.assign()`/`unassign()` and
`device_assignment_policy.assert_role_compatible_with_device_type()`
already carry the actual rules.

`AssignDeviceUseCase` deliberately does NOT auto-replace an existing
active assignment for the same (workstation, role) — `Device
AssignmentConflictError` already exists in the domain for exactly this
case (§20/§62: at most one active device per role), so a conflict is
surfaced clearly and the caller must `unassign()` the old one first, a
separate explicit action rather than a silent swap.
"""

from __future__ import annotations

from backend.domain.device_management.entities.workstation_device_assignment import (
    WorkstationDeviceAssignment,
)
from backend.domain.device_management.enums import AssignmentRole
from backend.domain.device_management.exceptions import (
    DeviceAssignmentConflictError,
    DeviceAssignmentNotFoundError,
    DeviceNotFoundError,
)
from backend.domain.device_management.policies.device_assignment_policy import (
    assert_role_compatible_with_device_type,
)
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.workstation_device_assignment_repository import (
    SqliteWorkstationDeviceAssignmentRepository,
)


class AssignDeviceUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._assignments = SqliteWorkstationDeviceAssignmentRepository(connection)
        self._devices = SqliteDeviceRepository(connection)
        self._profiles = SqliteDeviceProfileRepository(connection)

    def execute(
        self, *, workstation_id: str, device_id: str, role: AssignmentRole | str,
        assigned_by_user_id: str = "",
    ) -> WorkstationDeviceAssignment:
        role = AssignmentRole(role)
        device = self._devices.get(device_id)
        if device is None:
            raise DeviceNotFoundError(f"Dispositivo {device_id} no encontrado")
        profile = self._profiles.get(device.profile_id)
        if profile is not None:
            assert_role_compatible_with_device_type(role, profile.device_type)

        existing = self._assignments.get_active_for_role(workstation_id, role)
        if existing is not None:
            raise DeviceAssignmentConflictError(
                f"La estación ya tiene un dispositivo activo en el rol {role.value}; "
                "desasígnalo primero."
            )

        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=workstation_id, device_id=device_id, role=role,
            assigned_by_user_id=assigned_by_user_id or None,
        )
        self._assignments.save(assignment)
        self._conn.commit()
        return assignment


class UnassignDeviceUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._assignments = SqliteWorkstationDeviceAssignmentRepository(connection)

    def execute(self, *, assignment_id: str) -> WorkstationDeviceAssignment:
        assignment = self._assignments.get(assignment_id)
        if assignment is None:
            raise DeviceAssignmentNotFoundError(f"Asignación {assignment_id} no encontrada")
        assignment.unassign()
        self._assignments.save(assignment)
        self._conn.commit()
        return assignment
