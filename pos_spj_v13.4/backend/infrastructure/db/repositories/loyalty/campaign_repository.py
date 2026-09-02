"""CampaignRepository — persist/reconstruct `Campaign` (LOY-11, §19)."""

from __future__ import annotations

from backend.domain.loyalty.entities.campaign import Campaign
from backend.domain.loyalty.enums import CampaignStatus, CampaignType
from backend.infrastructure.db.repositories.loyalty.base import (
    LoyaltyRepositoryBase,
    opt_dec_str,
    to_decimal,
)


class CampaignRepository(LoyaltyRepositoryBase):
    def save(self, campaign: Campaign) -> None:
        self._execute(
            """
            INSERT INTO loyalty_campaigns (
                id, program_id, code, name, campaign_type, created_by_user_id,
                audience_definition, start_at, end_at, budget_limit, benefit_type,
                benefit_reference_id, branch_scope, channel_scope, frequency_cap,
                customer_cap, status, approved_by_user_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                audience_definition=excluded.audience_definition,
                start_at=excluded.start_at,
                end_at=excluded.end_at,
                budget_limit=excluded.budget_limit,
                benefit_type=excluded.benefit_type,
                benefit_reference_id=excluded.benefit_reference_id,
                branch_scope=excluded.branch_scope,
                channel_scope=excluded.channel_scope,
                frequency_cap=excluded.frequency_cap,
                customer_cap=excluded.customer_cap,
                status=excluded.status,
                approved_by_user_id=excluded.approved_by_user_id,
                updated_at=excluded.updated_at
            """,
            (
                campaign.id, campaign.program_id, campaign.code, campaign.name,
                campaign.campaign_type.value, campaign.created_by_user_id,
                campaign.audience_definition, campaign.start_at, campaign.end_at,
                opt_dec_str(campaign.budget_limit), campaign.benefit_type,
                campaign.benefit_reference_id, campaign.branch_scope,
                campaign.channel_scope, campaign.frequency_cap, campaign.customer_cap,
                campaign.status.value, campaign.approved_by_user_id, campaign.created_at,
                campaign.updated_at,
            ),
        )

    def get(self, campaign_id: str) -> Campaign | None:
        row = self._query_one("SELECT * FROM loyalty_campaigns WHERE id=?", (campaign_id,))
        return self._hydrate(row) if row else None

    def list_active_for_program(self, program_id: str) -> list[Campaign]:
        rows = self._query(
            "SELECT * FROM loyalty_campaigns WHERE program_id=? AND status='ACTIVE'"
            " ORDER BY name", (program_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> Campaign:
        return Campaign(
            id=row["id"], program_id=row["program_id"], code=row["code"], name=row["name"],
            campaign_type=CampaignType(row["campaign_type"]),
            created_by_user_id=row["created_by_user_id"],
            audience_definition=row["audience_definition"], start_at=row["start_at"],
            end_at=row["end_at"],
            budget_limit=(to_decimal(row["budget_limit"]) if row["budget_limit"] is not None
                          else None),
            benefit_type=row["benefit_type"], benefit_reference_id=row["benefit_reference_id"],
            branch_scope=row["branch_scope"], channel_scope=row["channel_scope"],
            frequency_cap=row["frequency_cap"], customer_cap=row["customer_cap"],
            status=CampaignStatus(row["status"]),
            approved_by_user_id=row["approved_by_user_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
