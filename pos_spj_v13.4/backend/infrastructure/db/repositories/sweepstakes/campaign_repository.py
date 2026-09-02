"""CampaignRepository / RuleRepository / PrizeRepository — persist/
reconstruct SweepstakesCampaign, SweepstakesRule, SweepstakesPrize (LOY-15,
§27)."""

from __future__ import annotations

from backend.domain.sweepstakes.entities.sweepstakes_campaign import SweepstakesCampaign
from backend.domain.sweepstakes.entities.sweepstakes_prize import SweepstakesPrize
from backend.domain.sweepstakes.entities.sweepstakes_rule import SweepstakesRule
from backend.domain.sweepstakes.enums import (
    SweepstakesCampaignStatus,
    SweepstakesEntryMethod,
    SweepstakesPrizeStatus,
)
from backend.infrastructure.db.repositories.sweepstakes.base import (
    SweepstakesRepositoryBase,
    bool_to_int,
    dec_str,
    int_to_bool,
    to_decimal,
)


class SweepstakesCampaignRepository(SweepstakesRepositoryBase):
    def save(self, campaign: SweepstakesCampaign) -> None:
        self._execute(
            """
            INSERT INTO sweepstakes_campaigns (
                id, code, name, description, ticket_price, max_tickets_per_customer,
                branch_id, status, starts_at, ends_at, created_by_user_id,
                approved_by_user_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                ticket_price=excluded.ticket_price,
                max_tickets_per_customer=excluded.max_tickets_per_customer,
                status=excluded.status,
                starts_at=excluded.starts_at,
                ends_at=excluded.ends_at,
                approved_by_user_id=excluded.approved_by_user_id,
                updated_at=excluded.updated_at
            """,
            (
                campaign.id, campaign.code, campaign.name, campaign.description,
                dec_str(campaign.ticket_price), campaign.max_tickets_per_customer,
                campaign.branch_id, campaign.status.value, campaign.starts_at, campaign.ends_at,
                campaign.created_by_user_id, campaign.approved_by_user_id,
                campaign.created_at, campaign.updated_at,
            ),
        )

    def get(self, campaign_id: str) -> SweepstakesCampaign | None:
        row = self._query_one("SELECT * FROM sweepstakes_campaigns WHERE id=?", (campaign_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> SweepstakesCampaign | None:
        row = self._query_one("SELECT * FROM sweepstakes_campaigns WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[SweepstakesCampaign]:
        rows = self._query("SELECT * FROM sweepstakes_campaigns WHERE status='ACTIVE'")
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> SweepstakesCampaign:
        return SweepstakesCampaign(
            id=row["id"], code=row["code"], name=row["name"], description=row["description"],
            ticket_price=to_decimal(row["ticket_price"]),
            max_tickets_per_customer=row["max_tickets_per_customer"], branch_id=row["branch_id"],
            status=SweepstakesCampaignStatus(row["status"]), starts_at=row["starts_at"],
            ends_at=row["ends_at"], created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SweepstakesRuleRepository(SweepstakesRepositoryBase):
    def save(self, rule: SweepstakesRule) -> None:
        self._execute(
            """
            INSERT INTO sweepstakes_rules (
                id, campaign_id, entry_method, amount_per_ticket, tickets_per_sale,
                max_tickets_per_sale, max_tickets_per_customer, requires_registered_customer,
                created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(campaign_id) DO UPDATE SET
                entry_method=excluded.entry_method,
                amount_per_ticket=excluded.amount_per_ticket,
                tickets_per_sale=excluded.tickets_per_sale,
                max_tickets_per_sale=excluded.max_tickets_per_sale,
                max_tickets_per_customer=excluded.max_tickets_per_customer,
                requires_registered_customer=excluded.requires_registered_customer
            """,
            (
                rule.id, rule.campaign_id, rule.entry_method.value, dec_str(rule.amount_per_ticket),
                rule.tickets_per_sale, rule.max_tickets_per_sale, rule.max_tickets_per_customer,
                bool_to_int(rule.requires_registered_customer), rule.created_at,
            ),
        )

    def get_by_campaign(self, campaign_id: str) -> SweepstakesRule | None:
        row = self._query_one(
            "SELECT * FROM sweepstakes_rules WHERE campaign_id=?", (campaign_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> SweepstakesRule:
        return SweepstakesRule(
            id=row["id"], campaign_id=row["campaign_id"],
            entry_method=SweepstakesEntryMethod(row["entry_method"]),
            amount_per_ticket=to_decimal(row["amount_per_ticket"]),
            tickets_per_sale=row["tickets_per_sale"],
            max_tickets_per_sale=row["max_tickets_per_sale"],
            max_tickets_per_customer=row["max_tickets_per_customer"],
            requires_registered_customer=int_to_bool(row["requires_registered_customer"]),
            created_at=row["created_at"],
        )


class SweepstakesPrizeRepository(SweepstakesRepositoryBase):
    def save(self, prize: SweepstakesPrize) -> None:
        self._execute(
            """
            INSERT INTO sweepstakes_prizes (
                id, campaign_id, name, description, quantity, rank, estimated_cost, status,
                created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                quantity=excluded.quantity,
                rank=excluded.rank,
                estimated_cost=excluded.estimated_cost,
                status=excluded.status
            """,
            (
                prize.id, prize.campaign_id, prize.name, prize.description, prize.quantity,
                prize.rank, dec_str(prize.estimated_cost), prize.status.value, prize.created_at,
            ),
        )

    def get(self, prize_id: str) -> SweepstakesPrize | None:
        row = self._query_one("SELECT * FROM sweepstakes_prizes WHERE id=?", (prize_id,))
        return self._hydrate(row) if row else None

    def list_for_campaign(self, campaign_id: str) -> list[SweepstakesPrize]:
        rows = self._query(
            "SELECT * FROM sweepstakes_prizes WHERE campaign_id=? ORDER BY rank",
            (campaign_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> SweepstakesPrize:
        return SweepstakesPrize(
            id=row["id"], campaign_id=row["campaign_id"], name=row["name"],
            description=row["description"], quantity=row["quantity"], rank=row["rank"],
            estimated_cost=to_decimal(row["estimated_cost"]),
            status=SweepstakesPrizeStatus(row["status"]), created_at=row["created_at"],
        )
