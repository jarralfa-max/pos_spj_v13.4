"""Composition root for the Fidelidad desktop module (LOY-25, LOY-29).

The ONLY place that wires a real, live ``connection``/``session_context``
into query services, command handlers and the presenter. Takes only plain
arguments — never the app's whole dependency container.

LOY-29: every action of the record pages (§6 sidebar) is bound here to an
EXISTING use case through ``_bind``: the presenter offers who/where/operation
(``actor_user_id``/``actor_branch_id``/``operation_id``) and ``_bind`` passes
each one only if that use case's ``execute`` declares it — use cases differ
(campaigns take no branch, sweepstakes forward ``**kwargs`` to the entity), and
an undeclared context key leaking into ``**kwargs`` would end up as an entity
field. Coupons/Vouchers/Sweepstakes cross into their own Units of Work but
share the ``GROWTH_ENGINE`` permission surface (LOY-1's design).
"""

from __future__ import annotations

import inspect

from backend.application.commercial_instruments.use_cases import coupon_use_cases as coupons
from backend.application.commercial_instruments.use_cases import voucher_use_cases as vouchers
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.queries.customer_lookup_query_service import (
    CustomerLookupQueryService,
)
from backend.application.customers.session_authorization import CustomerSessionPermissionChecker
from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.queries.member_profile_query_service import (
    LoyaltyMemberProfileQueryService,
)
from backend.application.loyalty.queries.records_query_service import LoyaltyRecordsQueryService
from backend.application.loyalty.session_authorization import LoyaltySessionPermissionChecker
from backend.application.loyalty.use_cases import (
    birthday_use_cases as birthdays,
    campaign_use_cases as campaigns,
    fraud_use_cases as fraud,
    gamification_use_cases as gamification,
    ledger_use_cases as ledger,
    membership_use_cases as memberships,
    program_use_cases as programs,
    referral_use_cases as referrals,
    reward_use_cases as rewards,
    tier_use_cases as tiers,
)
from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.session_authorization import (
    LoyaltyCardsSessionPermissionChecker,
)
from backend.application.sweepstakes.use_cases import (
    campaign_use_cases as sw_campaigns,
    draw_use_cases as sw_draws,
    entry_use_cases as sw_entries,
    winner_use_cases as sw_winners,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import SweepstakesUnitOfWork
from backend.shared.ids import new_uuid
from frontend.desktop.modules.fidelidad.fidelidad_presenter import FidelidadPresenter

#: Claves de contexto que el presenter siempre ofrece; sólo llegan al caso de uso
#: si su firma las declara.
_CONTEXT_KEYS = frozenset({"actor_user_id", "actor_branch_id", "operation_id"})


def _bind(connection, use_case_cls, auth, **defaults):
    params = inspect.signature(use_case_cls.execute).parameters

    def handler(**kwargs):
        valores = {**defaults, **kwargs}
        valores = {k: v for k, v in valores.items() if k not in _CONTEXT_KEYS or k in params}
        for clave, valor in list(valores.items()):
            if callable(valor) and clave in defaults and clave not in kwargs:
                valores[clave] = valor()
        return use_case_cls(auth).execute(connection, **valores)

    return handler


def _code(prefix: str):
    return lambda: f"{prefix}-{new_uuid()[-8:].upper()}"


def _list_active_programs(connection):
    with LoyaltyUnitOfWork(connection, owns_transaction=False) as uow:
        return uow.programs.list_active()


def _list_active_sweepstakes_campaigns(connection):
    with SweepstakesUnitOfWork(connection, owns_transaction=False) as uow:
        return uow.campaigns.list_active()


def _program_settings(connection):
    from backend.application.loyalty.queries.program_settings_query import (
        LoyaltyProgramSettingsQuery,
    )
    return LoyaltyProgramSettingsQuery(connection).current()


def _settings_use_case():
    from backend.application.loyalty.use_cases.program_settings_use_cases import (
        UpdateLoyaltyProgramSettingsUseCase,
    )
    return UpdateLoyaltyProgramSettingsUseCase


def _card_resolver(connection):
    from backend.application.loyalty_cards.queries.resolve_card_query import (
        ResolveLoyaltyCardQuery,
    )
    return ResolveLoyaltyCardQuery(connection)


def _authorizer_credentials(connection):
    from backend.security.authentication.verify_authorizer_credentials_use_case import (
        build_authorizer_credentials_verifier,
    )
    return build_authorizer_credentials_verifier(connection)


def _adjust_points_handler(connection, session_context):
    """Ajuste de puntos (§60): quien pide es la sesión; quien autoriza es OTRA
    persona con `puntos.ajustar`, validada contra `rol_permisos` (estándar único
    `AuthorizerPermissionChecker`, el mismo del POS)."""
    from backend.application.security.authorizer_permission_checker import (
        AuthorizerPermissionChecker,
    )
    from backend.application.security.session_or_authorizer_checker import (
        SessionOrAuthorizerPermissionChecker,
    )

    branch_id = getattr(session_context, "active_branch_id", None) or None
    policy = LoyaltyAuthorizationPolicy(SessionOrAuthorizerPermissionChecker(
        session=session_context,
        session_checker=LoyaltySessionPermissionChecker(session_context),
        authorizer_checker=AuthorizerPermissionChecker(connection, branch_id=branch_id)))

    def handler(*, actor_user_id, authorizer_user_id, **kw):
        return ledger.AdjustLoyaltyPointsUseCase(policy).execute(
            connection, requested_by=actor_user_id, authorizer_user_id=authorizer_user_id,
            **kw)

    return handler


def _card_render(connection):
    from backend.application.loyalty_cards.queries.card_render_data_query import (
        LoyaltyCardRenderDataQuery,
    )
    return LoyaltyCardRenderDataQuery(connection)


def _command_table(connection, auth) -> dict:
    b = lambda cls, **d: _bind(connection, cls, auth, **d)  # noqa: E731
    return {
        # programas
        "create_program": b(programs.CreateLoyaltyProgramUseCase),
        "approve_program": b(programs.ApproveLoyaltyProgramUseCase),
        "activate_program": b(programs.ActivateLoyaltyProgramUseCase),
        "suspend_program": b(programs.SuspendLoyaltyProgramUseCase),
        # membresías
        "enroll_membership": b(memberships.EnrollLoyaltyMembershipUseCase),
        "suspend_membership": b(memberships.SuspendLoyaltyMembershipUseCase),
        "close_membership": b(memberships.CloseLoyaltyMembershipUseCase),
        # puntos
        "accrue_points": b(ledger.AccrueLoyaltyPointsUseCase, source_module="fidelidad_ui"),
        "redeem_points": b(ledger.RedeemLoyaltyPointsUseCase, source_module="fidelidad_ui"),
        "reverse_transaction": b(ledger.ReverseLoyaltyTransactionUseCase),
        # niveles, recompensas, retos
        "create_tier": b(tiers.CreateLoyaltyTierUseCase),
        "create_reward": b(rewards.CreateRewardUseCase),
        "request_reward_redemption": b(rewards.RequestRewardRedemptionUseCase),
        "confirm_reward_redemption": b(rewards.ConfirmRewardRedemptionUseCase),
        "cancel_reward_redemption": b(rewards.CancelRewardRedemptionUseCase),
        "create_challenge": b(gamification.CreateLoyaltyChallengeUseCase),
        "activate_challenge": b(gamification.ActivateLoyaltyChallengeUseCase),
        # referidos
        "register_referral": b(referrals.RegisterReferralUseCase),
        "qualify_referral": b(referrals.QualifyReferralUseCase),
        "reward_referral": b(referrals.RewardReferralUseCase),
        "reject_referral": b(referrals.RejectReferralUseCase),
        "flag_referral_fraud": b(referrals.FlagReferralFraudSuspectedUseCase),
        # campañas y cumpleaños
        "create_campaign": b(campaigns.CreateCampaignUseCase),
        "approve_campaign": b(campaigns.ApproveCampaignUseCase),
        "schedule_campaign": b(campaigns.ScheduleCampaignUseCase),
        "activate_campaign": b(campaigns.ActivateCampaignUseCase),
        "pause_campaign": b(campaigns.PauseCampaignUseCase),
        "complete_campaign": b(campaigns.CompleteCampaignUseCase),
        "cancel_campaign": b(campaigns.CancelCampaignUseCase),
        "configure_birthday": b(birthdays.ConfigureBirthdayBenefitUseCase),
        # cupones y vales
        "create_coupon_definition": b(coupons.CreateCouponDefinitionUseCase),
        "issue_coupon": b(coupons.IssueCouponInstanceUseCase, code=_code("CUP")),
        "cancel_coupon": b(coupons.CancelCouponInstanceUseCase),
        "create_voucher_definition": b(vouchers.CreateVoucherDefinitionUseCase),
        "issue_voucher": b(vouchers.IssueVoucherInstanceUseCase, code=_code("VAL")),
        # sorteos
        "create_sweepstakes_campaign": b(sw_campaigns.CreateSweepstakesCampaignUseCase),
        "approve_sweepstakes_campaign": b(sw_campaigns.ApproveSweepstakesCampaignUseCase),
        "activate_sweepstakes_campaign": b(sw_campaigns.ActivateSweepstakesCampaignUseCase),
        "pause_sweepstakes_campaign": b(sw_campaigns.PauseSweepstakesCampaignUseCase),
        "resume_sweepstakes_campaign": b(sw_campaigns.ResumeSweepstakesCampaignUseCase),
        "close_sweepstakes_campaign": b(sw_campaigns.CloseSweepstakesCampaignUseCase),
        "cancel_sweepstakes_campaign": b(sw_campaigns.CancelSweepstakesCampaignUseCase),
        "configure_sweepstakes_rule": b(sw_campaigns.ConfigureSweepstakesRuleUseCase),
        "add_sweepstakes_prize": b(sw_campaigns.AddSweepstakesPrizeUseCase),
        "grant_sweepstakes_entry": b(sw_entries.GrantSweepstakesEntryUseCase),
        "issue_sweepstakes_ticket": b(sw_entries.IssueSweepstakesTicketUseCase),
        "print_sweepstakes_ticket": b(sw_entries.PrintSweepstakesTicketUseCase),
        "void_sweepstakes_ticket": b(sw_entries.VoidSweepstakesTicketUseCase),
        "schedule_sweepstakes_draw": b(sw_draws.ScheduleSweepstakesDrawUseCase),
        "execute_sweepstakes_draw": b(sw_draws.ExecuteSweepstakesDrawUseCase),
        "cancel_sweepstakes_draw": b(sw_draws.CancelSweepstakesDrawUseCase),
        "validate_sweepstakes_winner": b(sw_winners.ValidateSweepstakesWinnerUseCase),
        "disqualify_sweepstakes_winner": b(sw_winners.DisqualifySweepstakesWinnerUseCase),
        "deliver_sweepstakes_prize": b(sw_winners.DeliverSweepstakesPrizeUseCase),
        # antifraude
        "open_fraud_case": b(fraud.OpenFraudCaseUseCase),
        "start_fraud_review": b(fraud.StartFraudCaseReviewUseCase),
        "confirm_fraud_case": b(fraud.ConfirmFraudCaseUseCase),
        "dismiss_fraud_case": b(fraud.DismissFraudCaseUseCase),
    }


def _card_command_table(connection, cards_auth) -> dict:
    """Acciones de Tarjetas. Las que necesitan datos de otro contexto (cliente
    de una membresía, destinatarios de un lote, valores impresos por tarjeta)
    los obtienen de `LoyaltyCardRenderDataQuery`; el caso de uso decide."""
    from backend.application.loyalty_cards.queries.card_render_data_query import (
        LoyaltyCardRenderDataQuery,
    )
    from backend.application.loyalty_cards.result import LoyaltyCardResult
    from backend.application.loyalty_cards.use_cases import (
        batch_use_cases as cb,
        card_use_cases as cc,
        digital_card_use_cases as cd,
        import_use_cases as cim,
        print_use_cases as cpr,
        privacy_settings_use_cases as cps,
        sheet_use_cases as cs,
        template_use_cases as ct,
        token_use_cases as ctk,
    )

    datos = LoyaltyCardRenderDataQuery(connection)
    b = lambda cls, **d: _bind(connection, cls, cards_auth, **d)  # noqa: E731

    issue = b(cc.IssueLoyaltyCardUseCase)

    def issue_card(*, membership_id, **kw):
        customer_id = datos.customer_for_membership(membership_id)
        if not customer_id:
            return LoyaltyCardResult.fail("La membresía no existe.", "NOT_FOUND")
        return issue(membership_id=membership_id, customer_id=customer_id, **kw)

    create_batch = b(cb.CreateLoyaltyCardBatchUseCase)

    def create_card_batch(*, program_id, **kw):
        recipients = datos.recipients_without_card(program_id)
        if not recipients:
            return LoyaltyCardResult.fail(
                "Todas las membresías activas de ese programa ya tienen una tarjeta vigente.",
                "NOTHING_TO_DO")
        return create_batch(recipients=recipients, **kw)

    render = b(cpr.RenderLoyaltyCardBatchUseCase)

    def render_card_batch(*, batch_id, **kw):
        return render(batch_id=batch_id,
                      card_placeholder_values=datos.placeholders_for_batch(batch_id), **kw)

    reprint = b(cpr.ReprintLoyaltyCardBatchUseCase)

    def reprint_card_batch(*, original_job_id, **kw):
        batch_id = datos.batch_for_print_job(original_job_id)
        valores = datos.placeholders_for_batch(batch_id) if batch_id else {}
        return reprint(original_job_id=original_job_id, card_placeholder_values=valores, **kw)

    assign = b(cc.AssignLoyaltyCardUseCase)

    def assign_card(*, membership_id, **kw):
        dueno = datos.owner_of_membership(membership_id)
        if dueno is None:
            return LoyaltyCardResult.fail("La membresía no existe.", "NOT_FOUND")
        customer_id, account_id = dueno
        return assign(membership_id=membership_id, customer_id=customer_id,
                      loyalty_account_id=account_id, **kw)

    importar = b(cim.ImportLoyaltyCardDesignUseCase)
    formatos = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".svg": "SVG"}

    def import_card_design(*, file_path, **kw):
        """Lee el archivo elegido y lo entrega al caso de uso, que valida tipo,
        tamaño, dimensiones y contenido (SVG sin scripts ni enlaces)."""
        from pathlib import Path

        ruta = Path(file_path)
        formato = formatos.get(ruta.suffix.lower())
        if formato is None:
            return LoyaltyCardResult.fail(
                "Formato no admitido: usa PNG, JPEG o SVG.", "UNSUPPORTED_FORMAT")
        try:
            contenido = ruta.read_bytes()
        except OSError as exc:
            return LoyaltyCardResult.fail(f"No se pudo leer el archivo: {exc}", "FILE_ERROR")
        return importar(file_bytes=contenido, source_format=formato, **kw)

    def create_preprinted_batch(**kw):
        return create_batch(**kw)

    create_projection = b(cd.CreateLoyaltyDigitalCardProjectionUseCase)
    refresh_projection = b(cd.RefreshLoyaltyDigitalCardProjectionUseCase)

    def publish_digital_card(*, card_id, **kw):
        campos = datos.display_fields_for_card(card_id)
        accion = refresh_projection if datos.has_digital_projection(card_id) else create_projection
        return accion(card_id=card_id, display_fields=campos, **kw)

    return {
        "issue_card": issue_card,
        "assign_card": assign_card,
        "import_card_design": import_card_design,
        "create_preprinted_batch": create_preprinted_batch,
        "activate_card": b(cc.ActivateLoyaltyCardUseCase),
        "block_card": b(cc.BlockLoyaltyCardUseCase),
        "unblock_card": b(cc.UnblockLoyaltyCardUseCase),
        "replace_card": b(cc.ReplaceLoyaltyCardUseCase),
        "cancel_card": b(cc.CancelLoyaltyCardUseCase),
        "rotate_card_token": b(ctk.RotateLoyaltyCardTokenUseCase),
        "create_card_template": b(ct.CreateLoyaltyCardTemplateUseCase),
        "approve_card_template": b(ct.ApproveLoyaltyCardTemplateUseCase),
        "archive_card_template": b(ct.ArchiveLoyaltyCardTemplateUseCase),
        "save_card_design": b(ct.CreateLoyaltyCardTemplateVersionUseCase),
        "approve_card_template_version": b(ct.ApproveLoyaltyCardTemplateVersionUseCase),
        "activate_card_template_version": b(ct.ActivateLoyaltyCardTemplateVersionUseCase),
        "create_standard_sheet": b(cs.CreateStandard12x18SheetProfileUseCase),
        "create_sheet": b(cs.CreateSheetProfileUseCase),
        "create_imposition": b(cs.CreateImpositionProfileUseCase),
        "create_card_batch": create_card_batch,
        "submit_card_batch": b(cb.SubmitLoyaltyCardBatchForApprovalUseCase),
        "approve_card_batch": b(cb.ApproveLoyaltyCardBatchUseCase),
        "start_card_batch_printing": b(cb.StartLoyaltyCardBatchPrintingUseCase),
        "cancel_card_batch": b(cb.CancelLoyaltyCardBatchUseCase),
        "render_card_batch": render_card_batch,
        "reprint_card_batch": reprint_card_batch,
        "publish_digital_card": publish_digital_card,
        "update_card_privacy": b(cps.UpdateLoyaltyCardPrivacySettingsUseCase),
    }


def build_fidelidad_presenter(connection, session_context=None) -> FidelidadPresenter:
    checker = LoyaltySessionPermissionChecker(session_context)
    loyalty_auth = LoyaltyAuthorizationPolicy(checker)
    cards_auth = LoyaltyCardsAuthorizationPolicy(
        LoyaltyCardsSessionPermissionChecker(session_context))
    customer_auth = CustomerAuthorizationPolicy(CustomerSessionPermissionChecker(session_context))

    query_services = {
        "programs": lambda: _list_active_programs(connection),
        "member_profile": LoyaltyMemberProfileQueryService(connection),
        "sweepstakes_campaigns": lambda: _list_active_sweepstakes_campaigns(connection),
        "program_settings": lambda: _program_settings(connection),
        "records": LoyaltyRecordsQueryService(
            connection, authorization=loyalty_auth, cards_authorization=cards_auth),
        "customer_search": CustomerLookupQueryService(connection, customer_auth),
        "card_resolver": _card_resolver(connection),
        "card_render": _card_render(connection),
        "authorizer_credentials": _authorizer_credentials(connection),
    }

    def _legacy_shape(use_case_cls):
        """Handlers that the original LOY-25 pages call with explicit actor
        kwargs; kept so those pages keep working unchanged."""
        return lambda **kw: use_case_cls(loyalty_auth).execute(connection, **kw)

    command_handlers = _command_table(connection, loyalty_auth)
    command_handlers.update(_card_command_table(connection, cards_auth))
    command_handlers["adjust_points"] = _adjust_points_handler(connection, session_context)
    command_handlers.update({
        "update_program_settings": _legacy_shape(_settings_use_case()),
    })
    return FidelidadPresenter(
        session_context=session_context, query_services=query_services,
        command_handlers=command_handlers)


def create_fidelidad_view(connection, session_context=None, parent=None):
    """Factory used by the shell activator. Never receives the container
    itself — only what it needs, already unwrapped."""
    from frontend.desktop.modules.fidelidad.fidelidad_workspace import FidelidadWorkspace

    presenter = build_fidelidad_presenter(connection, session_context)
    return FidelidadWorkspace(presenter, parent)


__all__ = ["build_fidelidad_presenter", "create_fidelidad_view"]
