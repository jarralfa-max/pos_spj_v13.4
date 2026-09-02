"""LOY-11 — Campaign use cases: Create, Approve, Schedule, Activate, Pause,
Complete, Cancel (master prompt §19, phase list "LOY-11 — Campañas":
Audiencias, Aprobaciones, Vigencia, Límites).

Segregation of duties (§60) is enforced by the `Campaign` entity itself
(`approve()`/`activate()` reject a same-user attempt) — these use cases only
add the permission gate on top, mirroring `CreateLoyaltyProgramUseCase`'s
own approve/activate split (LOY-4).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.dto import CampaignDTO
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.campaign import Campaign
from backend.domain.loyalty.enums import CampaignType
from backend.domain.loyalty.exceptions import (
    CampaignNotFoundError,
    LoyaltyDomainError,
    LoyaltyProgramNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


class CreateCampaignUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, program_id: str, code: str, name: str,
        campaign_type: CampaignType, actor_user_id: str, operation_id: str,
        audience_definition: str = "", start_at: str | None = None,
        end_at: str | None = None, budget_limit: Decimal | None = None,
        benefit_type: str = "", benefit_reference_id: str | None = None,
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.CAMPAIGN_CREATE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            if uow.programs.get(program_id) is None:
                return fail_from_domain_error(
                    LoyaltyProgramNotFoundError(f"Programa {program_id} no existe"),
                    operation_id=operation_id)
            try:
                campaign = Campaign.create(
                    program_id, code, name, campaign_type, actor_user_id,
                    audience_definition=audience_definition, start_at=start_at,
                    end_at=end_at, budget_limit=budget_limit, benefit_type=benefit_type,
                    benefit_reference_id=benefit_reference_id)
                campaign.submit_for_approval()
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.campaigns.save(campaign)
        return LoyaltyResult.ok(
            "Campaña creada", entity_id=campaign.id, operation_id=operation_id,
            campaign=CampaignDTO.from_entity(campaign))


class _CampaignTransitionUseCase(_LoyaltyBaseUseCase):
    permission_code: str = ""
    success_message: str = ""

    def _transition(self, campaign: Campaign, **kwargs) -> None:
        raise NotImplementedError

    def execute(self, connection, *, campaign_id: str, actor_user_id: str,
                operation_id: str, **kwargs) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, self.permission_code)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            campaign = uow.campaigns.get(campaign_id)
            if campaign is None:
                return fail_from_domain_error(
                    CampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                    operation_id=operation_id)
            try:
                self._transition(campaign, actor_user_id=actor_user_id, **kwargs)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.campaigns.save(campaign)
        return LoyaltyResult.ok(self.success_message, entity_id=campaign.id,
                                operation_id=operation_id,
                                campaign=CampaignDTO.from_entity(campaign))


class ApproveCampaignUseCase(_CampaignTransitionUseCase):
    permission_code = LoyaltyPermissions.CAMPAIGN_APPROVE
    success_message = "Campaña aprobada"

    def _transition(self, campaign: Campaign, *, actor_user_id: str) -> None:
        campaign.approve(actor_user_id)


class ScheduleCampaignUseCase(_CampaignTransitionUseCase):
    permission_code = LoyaltyPermissions.CAMPAIGN_CREATE
    success_message = "Campaña programada"

    def _transition(self, campaign: Campaign, **_kwargs) -> None:
        campaign.schedule()


class ActivateCampaignUseCase(_CampaignTransitionUseCase):
    permission_code = LoyaltyPermissions.CAMPAIGN_ACTIVATE
    success_message = "Campaña activada"

    def _transition(self, campaign: Campaign, *, actor_user_id: str) -> None:
        campaign.activate(actor_user_id)


class PauseCampaignUseCase(_CampaignTransitionUseCase):
    permission_code = LoyaltyPermissions.CAMPAIGN_ACTIVATE
    success_message = "Campaña pausada"

    def _transition(self, campaign: Campaign, **_kwargs) -> None:
        campaign.pause()


class CompleteCampaignUseCase(_CampaignTransitionUseCase):
    permission_code = LoyaltyPermissions.CAMPAIGN_ACTIVATE
    success_message = "Campaña completada"

    def _transition(self, campaign: Campaign, **_kwargs) -> None:
        campaign.complete()


class CancelCampaignUseCase(_CampaignTransitionUseCase):
    permission_code = LoyaltyPermissions.CAMPAIGN_CREATE
    success_message = "Campaña cancelada"

    def execute(self, connection, *, campaign_id: str, reason: str, actor_user_id: str,
                operation_id: str) -> LoyaltyResult:
        return super().execute(connection, campaign_id=campaign_id,
                               actor_user_id=actor_user_id, operation_id=operation_id,
                               reason=reason)

    def _transition(self, campaign: Campaign, *, reason: str, **_kwargs) -> None:
        campaign.cancel(reason)
