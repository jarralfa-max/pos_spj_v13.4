"""Presenter bridge between the Fidelidad desktop UI and backend services
(LOY-25).

Mirrors ``frontend/desktop/modules/customers_crm/customers_crm_presenter.py``'s
thin-bridge shape: pages ask this presenter for capabilities and named
results, never touching a repository, a Unit of Work, or raw SQL
themselves, and never receiving the whole app's dependency container.
Every WRITE method goes through ``command_handlers`` (pre-bound by the
composition root to a real connection); every READ method goes through
``query_services``. Both degrade to a safe, non-raising result when
unwired (no live connection plugged in) rather than crashing a page.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from backend.application.commercial_instruments.result import (
    CommercialInstrumentResult,
)
from backend.application.loyalty.queries.member_profile_query_service import (
    LoyaltyMemberProfileView,
)
from backend.application.loyalty.result import LoyaltyResult
from backend.application.sweepstakes.result import SweepstakesResult
from backend.shared.ids import new_uuid
from frontend.desktop.modules.fidelidad.capability_resolver import (
    resolve_fidelidad_capabilities,
)
from frontend.desktop.modules.fidelidad.view_models import FidelidadCapabilities

_NOT_WIRED = "El módulo de Fidelidad no está disponible: falta la conexión al backend."


class FidelidadPresenter:
    def __init__(
        self, *, session_context,
        query_services: dict[str, object] | None = None,
        command_handlers: dict[str, Callable[..., object]] | None = None,
    ) -> None:
        self._session = session_context
        self._query_services = dict(query_services or {})
        self._command_handlers = dict(command_handlers or {})

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> FidelidadCapabilities:
        return resolve_fidelidad_capabilities(self.can)

    def current_user_id(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def current_branch_id(self) -> str:
        return str(getattr(self._session, "active_branch_id", "") or "")

    def query_service(self, key: str):
        return self._query_services.get(key)

    def command_handler(self, key: str) -> Callable[..., object] | None:
        return self._command_handlers.get(key)

    # -- Programas ------------------------------------------------------
    def list_programs(self) -> list:
        service = self.query_service("programs")
        return list(service()) if service is not None else []

    def create_program(self, *, code: str, name: str, currency_name: str,
                       description: str = "") -> LoyaltyResult:
        handler = self.command_handler("create_program")
        if handler is None:
            return LoyaltyResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            code=code, name=name, currency_name=currency_name, description=description,
            actor_user_id=self.current_user_id(), actor_branch_id=self.current_branch_id(),
            operation_id=new_uuid())

    def approve_program(self, program_id: str) -> LoyaltyResult:
        handler = self.command_handler("approve_program")
        if handler is None:
            return LoyaltyResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            program_id=program_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    def activate_program(self, program_id: str) -> LoyaltyResult:
        handler = self.command_handler("activate_program")
        if handler is None:
            return LoyaltyResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            program_id=program_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    # -- Miembros / puntos ------------------------------------------------
    def member_profile(self, customer_id: str) -> LoyaltyMemberProfileView:
        service = self.query_service("member_profile")
        if service is None:
            return LoyaltyMemberProfileView(found=False)
        return service.get_profile(customer_id)

    def enroll_membership(self, *, customer_id: str, program_id: str) -> LoyaltyResult:
        handler = self.command_handler("enroll_membership")
        if handler is None:
            return LoyaltyResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            customer_id=customer_id, program_id=program_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    def accrue_points(self, *, loyalty_account_id: str, points_amount: Decimal,
                      reason_code: str, membership_id: str | None = None) -> LoyaltyResult:
        handler = self.command_handler("accrue_points")
        if handler is None:
            return LoyaltyResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            loyalty_account_id=loyalty_account_id, points_amount=points_amount,
            source_module="fidelidad_ui", reason_code=reason_code, membership_id=membership_id,
            actor_user_id=self.current_user_id(), actor_branch_id=self.current_branch_id(),
            operation_id=new_uuid())

    def redeem_points(self, *, loyalty_account_id: str, points_amount: Decimal,
                      reason_code: str, membership_id: str | None = None) -> LoyaltyResult:
        handler = self.command_handler("redeem_points")
        if handler is None:
            return LoyaltyResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            loyalty_account_id=loyalty_account_id, points_amount=points_amount,
            source_module="fidelidad_ui", reason_code=reason_code, membership_id=membership_id,
            actor_user_id=self.current_user_id(), actor_branch_id=self.current_branch_id(),
            operation_id=new_uuid())

    # -- Recompensas -------------------------------------------------------
    def redeem_reward(self, *, reward_id: str, membership_id: str) -> LoyaltyResult:
        """Requests AND immediately confirms the redemption — a two-step
        reserve/confirm ledger dance under the hood (LOY-8), presented as
        one button/action to the cashier."""
        request_handler = self.command_handler("request_reward_redemption")
        confirm_handler = self.command_handler("confirm_reward_redemption")
        if request_handler is None or confirm_handler is None:
            return LoyaltyResult.fail(_NOT_WIRED, "NOT_WIRED")
        requested = request_handler(
            reward_id=reward_id, membership_id=membership_id,
            actor_user_id=self.current_user_id(), actor_branch_id=self.current_branch_id(),
            operation_id=new_uuid())
        if not requested.success:
            return requested
        return confirm_handler(
            redemption_id=requested.entity_id, actor_user_id=self.current_user_id(),
            operation_id=new_uuid())

    # -- Cupones / vales ----------------------------------------------------
    def issue_coupon(self, *, definition_id: str, customer_id: str) -> CommercialInstrumentResult:
        handler = self.command_handler("issue_coupon")
        if handler is None:
            return CommercialInstrumentResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            definition_id=definition_id, code=_generate_code("CUP"), customer_id=customer_id,
            actor_user_id=self.current_user_id(), actor_branch_id=self.current_branch_id(),
            operation_id=new_uuid())

    def issue_voucher(self, *, definition_id: str, customer_id: str,
                      amount: Decimal) -> CommercialInstrumentResult:
        handler = self.command_handler("issue_voucher")
        if handler is None:
            return CommercialInstrumentResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            definition_id=definition_id, code=_generate_code("VAL"), amount=amount,
            customer_id=customer_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    # -- Sorteos -------------------------------------------------------------
    def list_sweepstakes_campaigns(self) -> list:
        service = self.query_service("sweepstakes_campaigns")
        return list(service()) if service is not None else []

    def create_sweepstakes_campaign(self, *, code: str, name: str) -> SweepstakesResult:
        handler = self.command_handler("create_sweepstakes_campaign")
        if handler is None:
            return SweepstakesResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            code=code, name=name, actor_user_id=self.current_user_id(),
            operation_id=new_uuid())

    def approve_sweepstakes_campaign(self, campaign_id: str) -> SweepstakesResult:
        handler = self.command_handler("approve_sweepstakes_campaign")
        if handler is None:
            return SweepstakesResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            campaign_id=campaign_id, actor_user_id=self.current_user_id(),
            operation_id=new_uuid())

    def activate_sweepstakes_campaign(self, campaign_id: str) -> SweepstakesResult:
        handler = self.command_handler("activate_sweepstakes_campaign")
        if handler is None:
            return SweepstakesResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            campaign_id=campaign_id, actor_user_id=self.current_user_id(),
            operation_id=new_uuid())

    def add_sweepstakes_prize(self, *, campaign_id: str, name: str) -> SweepstakesResult:
        handler = self.command_handler("add_sweepstakes_prize")
        if handler is None:
            return SweepstakesResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            campaign_id=campaign_id, name=name, actor_user_id=self.current_user_id(),
            operation_id=new_uuid())

    def grant_sweepstakes_entry(self, *, campaign_id: str, customer_id: str,
                                chances_granted: int = 1) -> SweepstakesResult:
        from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
        handler = self.command_handler("grant_sweepstakes_entry")
        if handler is None:
            return SweepstakesResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            campaign_id=campaign_id, customer_id=customer_id,
            entry_method=SweepstakesEntryMethod.MANUAL_GRANT, chances_granted=chances_granted,
            actor_user_id=self.current_user_id(), operation_id=new_uuid())

    def issue_sweepstakes_ticket(self, *, campaign_id: str, entry_id: str) -> SweepstakesResult:
        handler = self.command_handler("issue_sweepstakes_ticket")
        if handler is None:
            return SweepstakesResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            campaign_id=campaign_id, entry_id=entry_id, actor_user_id=self.current_user_id(),
            operation_id=new_uuid())


def _generate_code(prefix: str) -> str:
    return f"{prefix}-{new_uuid()[-8:].upper()}"
