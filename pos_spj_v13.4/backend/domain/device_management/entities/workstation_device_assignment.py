"""WorkstationDeviceAssignment — SET-7 (§20): which device plays which
role at which workstation. At most one *active* assignment may exist per
(workstation, role) — enforced by the schema's partial unique index
(SET-7 infra); `unassign()` is how a role gets freed up for reassignment
rather than deleting history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.device_management.enums import AssignmentRole
from backend.domain.device_management.exceptions import DeviceTransitionNotAllowedError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class WorkstationDeviceAssignment:
    id: str
    workstation_id: str
    device_id: str
    role: AssignmentRole
    active: bool = True
    assigned_by_user_id: str | None = None
    assigned_at: str = field(default_factory=_utcnow_iso)
    unassigned_at: str | None = None

    # construction ------------------------------------------------------------
    @classmethod
    def assign(
        cls, *, workstation_id: str, device_id: str, role: AssignmentRole,
        assigned_by_user_id: str | None = None,
    ) -> "WorkstationDeviceAssignment":
        return cls(
            id=new_uuid(), workstation_id=validate_uuidv7(workstation_id),
            device_id=validate_uuidv7(device_id), role=role, assigned_by_user_id=assigned_by_user_id,
        )

    # behavior ------------------------------------------------------------------
    def unassign(self, *, at: datetime | None = None) -> None:
        if not self.active:
            raise DeviceTransitionNotAllowedError("La asignación ya está inactiva")
        self.active = False
        self.unassigned_at = (at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
