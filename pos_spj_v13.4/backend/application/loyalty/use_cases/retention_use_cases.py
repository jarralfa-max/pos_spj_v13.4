"""LOY-14 — Retention/win-back use case (master prompt §20).

§20's own flow: "BI identifica riesgo → Publica segmento → Fidelidad crea
campaña → Emite beneficio → Ventas registra uso → Finanzas reconoce efecto
→ BI mide resultado." Fidelidad's job is narrow: given an already-created,
already-approved, ACTIVE campaign (LOY-11's own lifecycle) targeting an
at-risk customer BI already identified, emit the ONE benefit that campaign
already declares (`Campaign.benefit_type`/`benefit_reference_id`, LOY-11) —
it does NOT build a second churn/risk model (§20's own explicit
prohibition), it only reacts.

System-triggered (mirrors `GrantBirthdayBenefitUseCase`'s own reasoning,
LOY-14) — reacting to a BI segment is not an authenticated human command.
Same scope restraint as the birthday benefit: only the POINTS benefit type
is implemented this phase; COUPON/VOUCHER are flagged, not fabricated,
consistent with `GrantBirthdayBenefitUseCase`'s own documented limitation.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import CampaignType
from backend.domain.loyalty.events import SYSTEM_ACTOR_ID, LoyaltyEvents
from backend.domain.loyalty.exceptions import (
    CampaignNotEligibleForBenefitError,
    CampaignNotFoundError,
    LoyaltyMembershipNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork

_ELIGIBLE_CAMPAIGN_TYPES = (CampaignType.WIN_BACK, CampaignType.RETENTION)


class TriggerCampaignBenefitUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, campaign_id: str, membership_id: str, actor_branch_id: str,
        operation_id: str,
    ) -> LoyaltyResult:
        with LoyaltyUnitOfWork(connection) as uow:
            campaign = uow.campaigns.get(campaign_id)
            if campaign is None:
                return fail_from_domain_error(
                    CampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                    operation_id=operation_id)
            if not campaign.is_active() or campaign.campaign_type not in _ELIGIBLE_CAMPAIGN_TYPES:
                return fail_from_domain_error(
                    CampaignNotEligibleForBenefitError(
                        "La campaña debe estar ACTIVE y ser de tipo WIN_BACK o RETENTION"),
                    operation_id=operation_id)
            membership = uow.memberships.get(membership_id)
            if membership is None:
                return fail_from_domain_error(
                    LoyaltyMembershipNotFoundError(f"Membresía {membership_id} no existe"),
                    operation_id=operation_id)
            if (campaign.benefit_type or "").upper() != "POINTS" or not campaign.benefit_reference_id:
                return LoyaltyResult.fail(
                    "Solo se implementa el beneficio POINTS para retención en esta fase",
                    "NOT_IMPLEMENTED", operation_id=operation_id)

            points_amount = Decimal(campaign.benefit_reference_id)
            bonus = LoyaltyTransaction.bonus(
                loyalty_account_id=membership.loyalty_account_id, points_amount=points_amount,
                operation_id=operation_id, membership_id=membership.id,
                source_module="loyalty_retention", reason_code=f"WINBACK:{campaign.code}",
                branch_id=actor_branch_id, created_by_user_id=SYSTEM_ACTOR_ID)
            uow.transactions.save(bonus)
            self._emit(uow, LoyaltyEvents.POINTS_ISSUED, entity_id=bonus.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=SYSTEM_ACTOR_ID, loyalty_transaction_id=bonus.id,
                       campaign_id=campaign.id, points_amount=str(points_amount))
        return LoyaltyResult.ok(
            "Beneficio de retención emitido", entity_id=bonus.id, operation_id=operation_id)
