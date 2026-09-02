"""CampaignPlacement — SET-18 "Placements": which `ContentCampaign`
currently occupies which `AdvertisingSlot`. Mirrors
`backend.domain.device_management.entities.workstation_device_assignment.
WorkstationDeviceAssignment`'s exact shape (SET-7) — at most one *active*
placement may exist per slot (enforced by the schema's partial unique
index, infra); `unassign()` is how a slot gets freed up for reassignment
rather than deleting history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_display.exceptions import AssignmentAlreadyInactiveError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CampaignPlacement:
    id: str
    campaign_id: str
    slot_id: str
    active: bool = True
    assigned_by_user_id: str | None = None
    assigned_at: str = field(default_factory=_utcnow_iso)
    unassigned_at: str | None = None

    # construction ------------------------------------------------------------
    @classmethod
    def assign(
        cls, *, campaign_id: str, slot_id: str, assigned_by_user_id: str | None = None,
    ) -> "CampaignPlacement":
        return cls(
            id=new_uuid(), campaign_id=validate_uuidv7(campaign_id), slot_id=validate_uuidv7(slot_id),
            assigned_by_user_id=assigned_by_user_id,
        )

    # behavior ------------------------------------------------------------------
    def unassign(self, *, at: datetime | None = None) -> None:
        if not self.active:
            raise AssignmentAlreadyInactiveError("La asignación ya está inactiva")
        self.active = False
        self.unassigned_at = (at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
