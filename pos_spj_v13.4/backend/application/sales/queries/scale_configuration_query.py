"""Resolve one explicit scale from the canonical device register."""
from backend.application.sales.permissions import SalesPermissions
from backend.domain.device_management.enums import AssignmentRole, DeviceType
from backend.domain.device_management.policies.scale_profile_policy import assert_valid_scale_profile
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.device_profile_repository import SqliteDeviceProfileRepository
from backend.infrastructure.db.repositories.device_management.workstation_device_assignment_repository import SqliteWorkstationDeviceAssignmentRepository
from backend.infrastructure.db.repositories.settings.workstation_repository import SqliteWorkstationRepository


class ScaleConfigurationQuery:
    def __init__(self, connection, authorization):
        self._devices = SqliteDeviceRepository(connection)
        self._profiles = SqliteDeviceProfileRepository(connection)
        self._auth = authorization
        self._assignments = SqliteWorkstationDeviceAssignmentRepository(connection)
        self._workstations = SqliteWorkstationRepository(connection)

    def resolve(self, *, actor_user_id, branch_id, workstation_id=None):
        self._auth.require(actor_user_id, SalesPermissions.SCALE_USE)
        self._auth.require_branch(actor_user_id, branch_id)
        assigned_device_id = None
        if workstation_id:
            workstation = self._workstations.get(workstation_id)
            if workstation is None or workstation.branch_id != branch_id or workstation.status.value != "ACTIVE":
                raise ValueError("La estación no está activa en la sucursal")
            assignment = self._assignments.get_active_for_role(workstation_id, AssignmentRole.SCALE)
            if assignment is None:
                return None
            assigned_device_id = assignment.device_id
        matches = []
        for device in self._devices.list_active():
            if device.branch_id != branch_id:
                continue
            if assigned_device_id and device.id != assigned_device_id:
                continue
            profile = self._profiles.get(device.profile_id)
            if profile and profile.active and profile.device_type == DeviceType.SCALE:
                assert_valid_scale_profile(profile)
                matches.append((device, profile))
        if len(matches) > 1:
            raise ValueError("Hay varias básculas en la sucursal; se requiere asignar la estación")
        return matches[0] if matches else None
