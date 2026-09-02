"""Sweepstakes campaign lifecycle + rule/prize configuration use cases
(LOY-15, master prompt §27). Mirrors
backend/application/loyalty/use_cases/campaign_use_cases.py's own
`_CampaignTransitionUseCase` DRY template."""

from __future__ import annotations

from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.sweepstakes.result import SweepstakesResult, fail_from_domain_error
from backend.application.sweepstakes.use_cases._base import _SweepstakesBaseUseCase
from backend.domain.sweepstakes.entities.sweepstakes_campaign import SweepstakesCampaign
from backend.domain.sweepstakes.entities.sweepstakes_prize import SweepstakesPrize
from backend.domain.sweepstakes.entities.sweepstakes_rule import SweepstakesRule
from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
from backend.domain.sweepstakes.events import SweepstakesEvents
from backend.domain.sweepstakes.exceptions import (
    SweepstakesCampaignNotFoundError,
    SweepstakesDomainError,
)
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import SweepstakesUnitOfWork


class CreateSweepstakesCampaignUseCase(_SweepstakesBaseUseCase):
    def execute(
        self, connection, *, code: str, name: str, actor_user_id: str, operation_id: str,
        **campaign_kwargs,
    ) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_MANAGE)
            with SweepstakesUnitOfWork(connection) as uow:
                campaign = SweepstakesCampaign.create(
                    code, name, created_by_user_id=actor_user_id, **campaign_kwargs)
                campaign.submit_for_approval()
                uow.campaigns.save(campaign)
                self._emit(uow, SweepstakesEvents.CAMPAIGN_CREATED, entity_id=campaign.id,
                           operation_id=operation_id, branch_id=campaign.branch_id or actor_user_id,
                           actor_user_id=actor_user_id)
            return SweepstakesResult.ok(
                "Campaña de sorteo creada", entity_id=campaign.id, operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class _SweepstakesCampaignTransitionUseCase(_SweepstakesBaseUseCase):
    permission_code: str = LoyaltyPermissions.SWEEPSTAKES_MANAGE
    success_message: str = ""
    event_name: str | None = None

    def _transition(self, campaign: SweepstakesCampaign, **kwargs) -> None:
        raise NotImplementedError

    def execute(self, connection, *, campaign_id: str, actor_user_id: str,
                operation_id: str, **kwargs) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, self.permission_code)
            with SweepstakesUnitOfWork(connection) as uow:
                campaign = uow.campaigns.get(campaign_id)
                if campaign is None:
                    return fail_from_domain_error(
                        SweepstakesCampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                        operation_id=operation_id)
                self._transition(campaign, actor_user_id=actor_user_id, **kwargs)
                uow.campaigns.save(campaign)
                if self.event_name is not None:
                    self._emit(uow, self.event_name, entity_id=campaign.id,
                               operation_id=operation_id,
                               branch_id=campaign.branch_id or actor_user_id,
                               actor_user_id=actor_user_id)
            return SweepstakesResult.ok(self.success_message, entity_id=campaign.id,
                                         operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ApproveSweepstakesCampaignUseCase(_SweepstakesCampaignTransitionUseCase):
    success_message = "Campaña aprobada"
    event_name = SweepstakesEvents.CAMPAIGN_APPROVED

    def _transition(self, campaign: SweepstakesCampaign, *, actor_user_id: str) -> None:
        campaign.approve(actor_user_id)


class ActivateSweepstakesCampaignUseCase(_SweepstakesCampaignTransitionUseCase):
    success_message = "Campaña activada"
    event_name = SweepstakesEvents.CAMPAIGN_ACTIVATED

    def _transition(self, campaign: SweepstakesCampaign, **_kwargs) -> None:
        campaign.activate()


class PauseSweepstakesCampaignUseCase(_SweepstakesCampaignTransitionUseCase):
    success_message = "Campaña pausada"

    def _transition(self, campaign: SweepstakesCampaign, **_kwargs) -> None:
        campaign.pause()


class ResumeSweepstakesCampaignUseCase(_SweepstakesCampaignTransitionUseCase):
    success_message = "Campaña reanudada"

    def _transition(self, campaign: SweepstakesCampaign, **_kwargs) -> None:
        campaign.resume()


class CloseSweepstakesCampaignUseCase(_SweepstakesCampaignTransitionUseCase):
    success_message = "Campaña cerrada"
    event_name = SweepstakesEvents.CAMPAIGN_CLOSED

    def _transition(self, campaign: SweepstakesCampaign, **_kwargs) -> None:
        campaign.close()


class CancelSweepstakesCampaignUseCase(_SweepstakesCampaignTransitionUseCase):
    success_message = "Campaña cancelada"
    event_name = SweepstakesEvents.CAMPAIGN_CANCELLED

    def _transition(self, campaign: SweepstakesCampaign, **_kwargs) -> None:
        campaign.cancel()


class ConfigureSweepstakesRuleUseCase(_SweepstakesBaseUseCase):
    def execute(
        self, connection, *, campaign_id: str, entry_method: SweepstakesEntryMethod,
        actor_user_id: str, operation_id: str, **rule_kwargs,
    ) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_MANAGE)
            with SweepstakesUnitOfWork(connection) as uow:
                campaign = uow.campaigns.get(campaign_id)
                if campaign is None:
                    return fail_from_domain_error(
                        SweepstakesCampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                        operation_id=operation_id)
                existing = uow.rules.get_by_campaign(campaign_id)
                if existing is not None:
                    rule = SweepstakesRule(id=existing.id, campaign_id=campaign_id,
                                            entry_method=entry_method, **rule_kwargs)
                else:
                    rule = SweepstakesRule.create(campaign_id, entry_method, **rule_kwargs)
                uow.rules.save(rule)
            return SweepstakesResult.ok(
                "Regla de sorteo configurada", entity_id=rule.id, operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class AddSweepstakesPrizeUseCase(_SweepstakesBaseUseCase):
    def execute(
        self, connection, *, campaign_id: str, name: str, actor_user_id: str,
        operation_id: str, **prize_kwargs,
    ) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_MANAGE)
            with SweepstakesUnitOfWork(connection) as uow:
                campaign = uow.campaigns.get(campaign_id)
                if campaign is None:
                    return fail_from_domain_error(
                        SweepstakesCampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                        operation_id=operation_id)
                prize = SweepstakesPrize.create(campaign_id, name, **prize_kwargs)
                uow.prizes.save(prize)
            return SweepstakesResult.ok(
                "Premio agregado", entity_id=prize.id, operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
