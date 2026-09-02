"""Composition root for the Fidelidad desktop module (LOY-25).

Mirrors ``frontend/desktop/modules/customers_crm/composition.py``'s shape:
the ONLY place that wires a real, live ``connection``/``session_context``
into query services, command handlers and the presenter. Takes only plain
arguments — never the app's whole dependency container.

Coupons/Vouchers/Sweepstakes command handlers cross into their own bounded
contexts' Unit of Work (``CommercialInstrumentsUnitOfWork``/
``SweepstakesUnitOfWork``) even though they're reached from the same
Fidelidad UI surface — matching LOY-1's own design (they share the
``GROWTH_ENGINE`` permission/nav surface without belonging to the Loyalty
bounded context itself).
"""

from __future__ import annotations

from backend.application.commercial_instruments.use_cases.coupon_use_cases import (
    IssueCouponInstanceUseCase,
)
from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
    IssueVoucherInstanceUseCase,
)
from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.queries.member_profile_query_service import (
    LoyaltyMemberProfileQueryService,
)
from backend.application.loyalty.session_authorization import LoyaltySessionPermissionChecker
from backend.application.loyalty.use_cases.ledger_use_cases import (
    AccrueLoyaltyPointsUseCase,
    RedeemLoyaltyPointsUseCase,
)
from backend.application.loyalty.use_cases.membership_use_cases import (
    EnrollLoyaltyMembershipUseCase,
)
from backend.application.loyalty.use_cases.program_use_cases import (
    ActivateLoyaltyProgramUseCase,
    ApproveLoyaltyProgramUseCase,
    CreateLoyaltyProgramUseCase,
)
from backend.application.loyalty.use_cases.reward_use_cases import (
    ConfirmRewardRedemptionUseCase,
    RequestRewardRedemptionUseCase,
)
from backend.application.sweepstakes.use_cases.campaign_use_cases import (
    ActivateSweepstakesCampaignUseCase,
    AddSweepstakesPrizeUseCase,
    ApproveSweepstakesCampaignUseCase,
    ConfigureSweepstakesRuleUseCase,
    CreateSweepstakesCampaignUseCase,
)
from backend.application.sweepstakes.use_cases.entry_use_cases import (
    GrantSweepstakesEntryUseCase,
    IssueSweepstakesTicketUseCase,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import SweepstakesUnitOfWork
from frontend.desktop.modules.fidelidad.fidelidad_presenter import FidelidadPresenter


def _list_active_programs(connection):
    with LoyaltyUnitOfWork(connection, owns_transaction=False) as uow:
        return uow.programs.list_active()


def _list_active_sweepstakes_campaigns(connection):
    with SweepstakesUnitOfWork(connection, owns_transaction=False) as uow:
        return uow.campaigns.list_active()


def build_fidelidad_presenter(connection, session_context=None) -> FidelidadPresenter:
    checker = LoyaltySessionPermissionChecker(session_context)
    loyalty_auth = LoyaltyAuthorizationPolicy(checker)
    sweepstakes_auth = LoyaltyAuthorizationPolicy(checker)

    query_services = {
        "programs": lambda: _list_active_programs(connection),
        "member_profile": LoyaltyMemberProfileQueryService(connection),
        "sweepstakes_campaigns": lambda: _list_active_sweepstakes_campaigns(connection),
    }

    def _run(use_case_cls, auth, **kwargs):
        return use_case_cls(auth).execute(connection, **kwargs)

    command_handlers = {
        "create_program": lambda **kw: _run(CreateLoyaltyProgramUseCase, loyalty_auth, **kw),
        "approve_program": lambda **kw: _run(ApproveLoyaltyProgramUseCase, loyalty_auth, **kw),
        "activate_program": lambda **kw: _run(ActivateLoyaltyProgramUseCase, loyalty_auth, **kw),
        "enroll_membership": lambda **kw: _run(
            EnrollLoyaltyMembershipUseCase, loyalty_auth, **kw),
        "accrue_points": lambda **kw: _run(AccrueLoyaltyPointsUseCase, loyalty_auth, **kw),
        "redeem_points": lambda **kw: _run(RedeemLoyaltyPointsUseCase, loyalty_auth, **kw),
        "request_reward_redemption": lambda **kw: _run(
            RequestRewardRedemptionUseCase, loyalty_auth, **kw),
        "confirm_reward_redemption": lambda **kw: _run(
            ConfirmRewardRedemptionUseCase, loyalty_auth, **kw),
        "issue_coupon": lambda **kw: _run(IssueCouponInstanceUseCase, loyalty_auth, **kw),
        "issue_voucher": lambda **kw: _run(IssueVoucherInstanceUseCase, loyalty_auth, **kw),
        "create_sweepstakes_campaign": lambda **kw: _run(
            CreateSweepstakesCampaignUseCase, sweepstakes_auth, **kw),
        "approve_sweepstakes_campaign": lambda **kw: _run(
            ApproveSweepstakesCampaignUseCase, sweepstakes_auth, **kw),
        "activate_sweepstakes_campaign": lambda **kw: _run(
            ActivateSweepstakesCampaignUseCase, sweepstakes_auth, **kw),
        "configure_sweepstakes_rule": lambda **kw: _run(
            ConfigureSweepstakesRuleUseCase, sweepstakes_auth, **kw),
        "add_sweepstakes_prize": lambda **kw: _run(
            AddSweepstakesPrizeUseCase, sweepstakes_auth, **kw),
        "grant_sweepstakes_entry": lambda **kw: _run(
            GrantSweepstakesEntryUseCase, sweepstakes_auth, **kw),
        "issue_sweepstakes_ticket": lambda **kw: _run(
            IssueSweepstakesTicketUseCase, sweepstakes_auth, **kw),
    }

    return FidelidadPresenter(
        session_context=session_context, query_services=query_services,
        command_handlers=command_handlers)


def create_fidelidad_view(connection, session_context=None, parent=None):
    """Factory used by ``modulos/fidelidad_enterprise.py``. Never receives
    the container itself — only what it needs, already unwrapped."""
    from frontend.desktop.modules.fidelidad.fidelidad_workspace import FidelidadWorkspace

    presenter = build_fidelidad_presenter(connection, session_context)
    return FidelidadWorkspace(presenter, parent)
