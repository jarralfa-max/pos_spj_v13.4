"""AssetAssignment — custody/responsibility record (ASSET-4, §19).

A full history: returning an assignment never overwrites it, it closes it
(sets ``returned_at``) and a new assignment is created for the next
custodian. Never mutate a closed record's custodian.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetAssignmentType
from backend.domain.assets.exceptions import AssetDomainError, AssetStateInvalidError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetAssignment:
    id: str
    asset_id: str
    assignment_type: AssetAssignmentType
    branch_id: str
    operation_id: str
    employee_id: str | None = None
    user_id: str | None = None
    location_id: str | None = None
    assigned_by: str | None = None
    condition_at_assignment: str | None = None
    condition_at_return: str | None = None
    notes: str = ""
    assigned_at: str = field(default_factory=_utcnow)
    returned_at: str | None = None

    @classmethod
    def create(cls, asset_id: str, assignment_type: AssetAssignmentType, branch_id: str,
               operation_id: str, *, employee_id: str | None = None,
               user_id: str | None = None, location_id: str | None = None,
               assigned_by: str | None = None,
               condition_at_assignment: str | None = None) -> "AssetAssignment":
        if not asset_id:
            raise AssetDomainError("AssetAssignment.asset_id is required")
        if not branch_id:
            raise AssetDomainError("AssetAssignment.branch_id is required")
        if not employee_id and not user_id:
            raise AssetDomainError(
                "AssetAssignment requires either employee_id or user_id (§19)")
        return cls(
            id=new_uuid(), asset_id=asset_id, assignment_type=assignment_type,
            branch_id=branch_id, operation_id=operation_id, employee_id=employee_id,
            user_id=user_id, location_id=location_id, assigned_by=assigned_by,
            condition_at_assignment=condition_at_assignment,
        )

    def is_active(self) -> bool:
        return self.returned_at is None

    def return_custody(self, condition_at_return: str | None = None) -> None:
        if self.returned_at is not None:
            raise AssetStateInvalidError("Esta custodia ya fue devuelta")
        self.returned_at = _utcnow()
        self.condition_at_return = condition_at_return
