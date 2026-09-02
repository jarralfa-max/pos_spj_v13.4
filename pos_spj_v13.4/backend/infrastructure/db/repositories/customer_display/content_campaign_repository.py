"""SqliteContentCampaignRepository — persists `ContentCampaign` (SET-18).
Implements
`backend.domain.customer_display.repository_ports.ContentCampaignRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.content_campaign import ContentCampaign
from backend.domain.customer_display.enums import ContentCampaignStatus
from backend.infrastructure.db.repositories.customer_display.base import CustomerDisplayRepositoryBase

_COLS = (
    "id, name, content_id, status, starts_at, ends_at, created_by_user_id, approved_by_user_id,"
    " activated_by_user_id, reason, created_at, updated_at"
)


class SqliteContentCampaignRepository(CustomerDisplayRepositoryBase):
    def save(self, campaign: ContentCampaign) -> None:
        self._execute(
            f"INSERT INTO content_campaigns ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " status=excluded.status, starts_at=excluded.starts_at, ends_at=excluded.ends_at,"
            " approved_by_user_id=excluded.approved_by_user_id,"
            " activated_by_user_id=excluded.activated_by_user_id, reason=excluded.reason,"
            " updated_at=excluded.updated_at",
            self._params(campaign),
        )

    def get(self, campaign_id: str) -> ContentCampaign | None:
        row = self._query_one(f"SELECT {_COLS} FROM content_campaigns WHERE id=?", (campaign_id,))
        return self._hydrate(row) if row else None

    def list_by_status(self, status: str) -> list[ContentCampaign]:
        rows = self._query(f"SELECT {_COLS} FROM content_campaigns WHERE status=?", (status,))
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[ContentCampaign]:
        rows = self._query(f"SELECT {_COLS} FROM content_campaigns ORDER BY name")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(campaign: ContentCampaign) -> tuple:
        return (
            campaign.id, campaign.name, campaign.content_id, campaign.status.value, campaign.starts_at,
            campaign.ends_at, campaign.created_by_user_id, campaign.approved_by_user_id,
            campaign.activated_by_user_id, campaign.reason, campaign.created_at, campaign.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> ContentCampaign:
        return ContentCampaign(
            id=row["id"], name=row["name"], content_id=row["content_id"],
            status=ContentCampaignStatus(row["status"]), starts_at=row["starts_at"], ends_at=row["ends_at"],
            created_by_user_id=row["created_by_user_id"], approved_by_user_id=row["approved_by_user_id"],
            activated_by_user_id=row["activated_by_user_id"], reason=row["reason"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
