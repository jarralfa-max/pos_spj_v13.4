"""Use cases for the "Campañas de marketing" card on the Configuración
Documentos page — SET-13 cutover. Same shape as
`document_template_use_cases.py`: thin orchestration over
`backend/domain/document_output/` (SET-13), construct/mutate the entity,
persist.

`CreateMarketingCampaignUseCase` validates responsible-FOMO
(`assert_responsible_claim`) BEFORE saving — a FOMO campaign with zero
rules must never reach the database, since `SalesMarketingClient`'s live
selection would otherwise have to discover the violation at print time
and skip it. `UpdateMarketingCampaignUseCase` re-validates for the same
reason: rules can be edited away from an existing FOMO campaign, and the
same invariant must hold after an edit as after a create.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.document_output.entities.marketing_campaign import MarketingCampaign
from backend.domain.document_output.enums import MarketingMessageCategory
from backend.domain.document_output.exceptions import MarketingCampaignNotFoundError
from backend.domain.document_output.policies.marketing_claim_validation_policy import assert_responsible_claim
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from backend.infrastructure.db.repositories.document_output.marketing_campaign_repository import (
    SqliteMarketingCampaignRepository,
)


class MarketingCampaignStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class CreateMarketingCampaignUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._campaigns = SqliteMarketingCampaignRepository(connection)

    def execute(
        self, *, code: str, category: MarketingMessageCategory | str, message_template: str,
        priority: int = 0, requires_customer: bool = False,
        rules: tuple[CampaignRule, ...] | list[CampaignRule] = (),
    ) -> MarketingCampaign:
        campaign = MarketingCampaign.create(
            code=code, category=MarketingMessageCategory(category), message_template=message_template,
            priority=priority, requires_customer=requires_customer, rules=rules,
        )
        assert_responsible_claim(campaign)
        self._campaigns.save(campaign)
        self._conn.commit()
        return campaign


class UpdateMarketingCampaignUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._campaigns = SqliteMarketingCampaignRepository(connection)

    def execute(
        self, *, campaign_id: str, message_template: str, priority: int = 0,
        requires_customer: bool = False, rules: tuple[CampaignRule, ...] | list[CampaignRule] = (),
    ) -> MarketingCampaign:
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            raise MarketingCampaignNotFoundError(f"Campaña {campaign_id} no encontrada")
        campaign.update_details(
            message_template=message_template, priority=priority, requires_customer=requires_customer,
            rules=rules,
        )
        assert_responsible_claim(campaign)
        self._campaigns.save(campaign)
        self._conn.commit()
        return campaign


class ChangeMarketingCampaignStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._campaigns = SqliteMarketingCampaignRepository(connection)

    def execute(self, *, campaign_id: str, action: MarketingCampaignStatusAction) -> MarketingCampaign:
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            raise MarketingCampaignNotFoundError(f"Campaña {campaign_id} no encontrada")

        if action is MarketingCampaignStatusAction.ACTIVATE:
            campaign.activate()
        elif action is MarketingCampaignStatusAction.DEACTIVATE:
            campaign.deactivate()

        self._campaigns.save(campaign)
        self._conn.commit()
        return campaign
