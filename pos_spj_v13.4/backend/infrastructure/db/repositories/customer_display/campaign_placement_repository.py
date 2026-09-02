"""SqliteCampaignPlacementRepository — persists `CampaignPlacement`
(SET-18). Implements
`backend.domain.customer_display.repository_ports.CampaignPlacementRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.campaign_placement import CampaignPlacement
from backend.infrastructure.db.repositories.customer_display.base import CustomerDisplayRepositoryBase

_COLS = "id, campaign_id, slot_id, active, assigned_by_user_id, assigned_at, unassigned_at"


class SqliteCampaignPlacementRepository(CustomerDisplayRepositoryBase):
    def save(self, placement: CampaignPlacement) -> None:
        self._execute(
            f"INSERT INTO campaign_placements ({_COLS})"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " active=excluded.active, unassigned_at=excluded.unassigned_at",
            self._params(placement),
        )

    def get(self, placement_id: str) -> CampaignPlacement | None:
        row = self._query_one(f"SELECT {_COLS} FROM campaign_placements WHERE id=?", (placement_id,))
        return self._hydrate(row) if row else None

    def get_active_for_slot(self, slot_id: str) -> CampaignPlacement | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM campaign_placements WHERE slot_id=? AND active=1", (slot_id,),
        )
        return self._hydrate(row) if row else None

    def list_for_campaign(self, campaign_id: str) -> list[CampaignPlacement]:
        rows = self._query(
            f"SELECT {_COLS} FROM campaign_placements WHERE campaign_id=? ORDER BY assigned_at DESC",
            (campaign_id,),
        )
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[CampaignPlacement]:
        rows = self._query(f"SELECT {_COLS} FROM campaign_placements ORDER BY assigned_at DESC")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(placement: CampaignPlacement) -> tuple:
        return (
            placement.id, placement.campaign_id, placement.slot_id, int(placement.active),
            placement.assigned_by_user_id, placement.assigned_at, placement.unassigned_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CampaignPlacement:
        return CampaignPlacement(
            id=row["id"], campaign_id=row["campaign_id"], slot_id=row["slot_id"], active=bool(row["active"]),
            assigned_by_user_id=row["assigned_by_user_id"], assigned_at=row["assigned_at"],
            unassigned_at=row["unassigned_at"],
        )
