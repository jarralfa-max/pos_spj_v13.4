"""SqliteMarketingCampaignRepository — persists `MarketingCampaign`
(SET-13). Implements
`backend.domain.document_output.repository_ports.MarketingCampaignRepositoryPort`.

`rules_json` serializes each `CampaignRule` as `{"metric", "comparator",
"threshold"}` with `threshold` as a JSON *string* (never a JSON number) —
same Decimal round-tripping discipline
`backend/infrastructure/db/repositories/settings/value_serialization.py`
uses for persisted Decimal values.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.domain.document_output.entities.marketing_campaign import MarketingCampaign
from backend.domain.document_output.enums import MarketingMessageCategory, RuleComparator
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from backend.infrastructure.db.repositories.document_output.base import DocumentOutputRepositoryBase

_COLS = (
    "id, code, category, message_template, priority, requires_customer, rules_json, active,"
    " created_at, updated_at"
)


class SqliteMarketingCampaignRepository(DocumentOutputRepositoryBase):
    def save(self, campaign: MarketingCampaign) -> None:
        self._execute(
            f"INSERT INTO marketing_campaigns ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " message_template=excluded.message_template, priority=excluded.priority,"
            " requires_customer=excluded.requires_customer, rules_json=excluded.rules_json,"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(campaign),
        )

    def get(self, campaign_id: str) -> MarketingCampaign | None:
        row = self._query_one(f"SELECT {_COLS} FROM marketing_campaigns WHERE id=?", (campaign_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> MarketingCampaign | None:
        row = self._query_one(f"SELECT {_COLS} FROM marketing_campaigns WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[MarketingCampaign]:
        rows = self._query(f"SELECT {_COLS} FROM marketing_campaigns WHERE active=1 ORDER BY priority DESC")
        return [self._hydrate(row) for row in rows]

    def list_active_by_category(self, category: MarketingMessageCategory) -> list[MarketingCampaign]:
        rows = self._query(
            f"SELECT {_COLS} FROM marketing_campaigns WHERE active=1 AND category=? ORDER BY priority DESC",
            (category.value,),
        )
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[MarketingCampaign]:
        rows = self._query(f"SELECT {_COLS} FROM marketing_campaigns ORDER BY code")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(campaign: MarketingCampaign) -> tuple:
        return (
            campaign.id, campaign.code, campaign.category.value, campaign.message_template,
            campaign.priority, int(campaign.requires_customer), _serialize_rules(campaign.rules),
            int(campaign.active), campaign.created_at, campaign.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> MarketingCampaign:
        return MarketingCampaign(
            id=row["id"], code=row["code"], category=MarketingMessageCategory(row["category"]),
            message_template=row["message_template"], priority=row["priority"],
            requires_customer=bool(row["requires_customer"]), rules=_deserialize_rules(row["rules_json"]),
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )


def _serialize_rules(rules: tuple[CampaignRule, ...]) -> str:
    return json.dumps([
        {"metric": rule.metric, "comparator": rule.comparator.value, "threshold": str(rule.threshold)}
        for rule in rules
    ])


def _deserialize_rules(raw: str) -> tuple[CampaignRule, ...]:
    return tuple(
        CampaignRule(
            metric=entry["metric"], comparator=RuleComparator(entry["comparator"]),
            threshold=Decimal(entry["threshold"]),
        )
        for entry in json.loads(raw or "[]")
    )
