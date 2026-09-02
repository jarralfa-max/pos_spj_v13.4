"""SqliteWorkstationDeviceAssignmentRepository — persists
`WorkstationDeviceAssignment` (SET-7). Implements
`backend.domain.device_management.repository_ports.WorkstationDeviceAssignmentRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.device_management.entities.workstation_device_assignment import (
    WorkstationDeviceAssignment,
)
from backend.domain.device_management.enums import AssignmentRole
from backend.infrastructure.db.repositories.device_management.base import DeviceManagementRepositoryBase

_COLS = (
    "id, workstation_id, device_id, role, active, assigned_by_user_id, assigned_at, unassigned_at"
)


class SqliteWorkstationDeviceAssignmentRepository(DeviceManagementRepositoryBase):
    def save(self, assignment: WorkstationDeviceAssignment) -> None:
        self._execute(
            f"INSERT INTO workstation_device_assignments ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " active=excluded.active, unassigned_at=excluded.unassigned_at",
            self._params(assignment),
        )

    def get(self, assignment_id: str) -> WorkstationDeviceAssignment | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM workstation_device_assignments WHERE id=?", (assignment_id,),
        )
        return self._hydrate(row) if row else None

    def get_active_for_role(
        self, workstation_id: str, role: AssignmentRole,
    ) -> WorkstationDeviceAssignment | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM workstation_device_assignments"
            " WHERE workstation_id=? AND role=? AND active=1",
            (workstation_id, role.value),
        )
        return self._hydrate(row) if row else None

    def list_active_for_workstation(self, workstation_id: str) -> list[WorkstationDeviceAssignment]:
        rows = self._query(
            f"SELECT {_COLS} FROM workstation_device_assignments"
            " WHERE workstation_id=? AND active=1 ORDER BY role",
            (workstation_id,),
        )
        return [self._hydrate(row) for row in rows]

    def list_for_device(self, device_id: str) -> list[WorkstationDeviceAssignment]:
        rows = self._query(
            f"SELECT {_COLS} FROM workstation_device_assignments"
            " WHERE device_id=? ORDER BY assigned_at DESC",
            (device_id,),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(assignment: WorkstationDeviceAssignment) -> tuple:
        return (
            assignment.id, assignment.workstation_id, assignment.device_id, assignment.role.value,
            int(assignment.active), assignment.assigned_by_user_id, assignment.assigned_at,
            assignment.unassigned_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> WorkstationDeviceAssignment:
        return WorkstationDeviceAssignment(
            id=row["id"], workstation_id=row["workstation_id"], device_id=row["device_id"],
            role=AssignmentRole(row["role"]), active=bool(row["active"]),
            assigned_by_user_id=row["assigned_by_user_id"], assigned_at=row["assigned_at"],
            unassigned_at=row["unassigned_at"],
        )
