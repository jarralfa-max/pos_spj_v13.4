"""Catálogo de páginas de registros de Fidelidad (LOY-29).

Cada entrada declara una pantalla del sidebar (§6): registro, columnas,
filtro por estado y acciones con su permiso granular (§59). Las acciones sólo
llaman a casos de uso ya existentes; los nombres de `command` son las llaves
que cablea `composition.py`.
"""

from __future__ import annotations

from backend.application.loyalty.integrations.finance_posting import (
    LoyaltyFinancePostingStatus,
    LoyaltyFinanceSourceType,
)
from backend.application.loyalty.permissions import LoyaltyPermissions as LP
from backend.application.loyalty.queries.records_query_service import LoyaltyRecord as R
from backend.domain.commercial_instruments.enums import (
    CommercialBenefitType,
    CouponInstanceStatus,
    CouponType,
    VoucherInstanceStatus,
    VoucherType,
)
from backend.domain.loyalty.enums import (
    AccountStatus,
    BirthdayBenefitType,
    CampaignStatus,
    CampaignType,
    ChallengeCriteriaType,
    ChallengeMode,
    ChallengeStatus,
    FraudCaseStatus,
    FraudCaseSubjectType,
    MembershipStatus,
    ProgramStatus,
    ReferralStatus,
    RewardRedemptionStatus,
    RewardType,
    TierEvaluationMethod,
    TransactionType,
)
from backend.domain.sweepstakes.enums import (
    SweepstakesCampaignStatus,
    SweepstakesDrawStatus,
    SweepstakesEntryMethod,
    SweepstakesPrizeStatus,
    SweepstakesTicketStatus,
    SweepstakesWinnerStatus,
)
from frontend.desktop.modules.fidelidad.records.specs import (
    ActionSpec as A,
    ColumnDef as C,
    FieldKind as K,
    FieldSpec as F,
    RecordPageSpec as P,
    TabbedSpec,
)

_MOTIVO = F("reason", "Motivo", K.MULTILINE)
_PROGRAMA = F("program_id", "Programa", K.RECORD, record=R.PROGRAMS,
              record_label=("name", "code"), record_filters={"status": "ACTIVE"})
_MEMBRESIA = F("membership_id", "Membresía", K.RECORD, record=R.MEMBERSHIPS,
               record_label=("customer_name", "program_name"),
               record_filters={"status": "ACTIVE"})

# ── Programas ───────────────────────────────────────────────────────────────
PROGRAMS = P(
    key="programs", title="Programas", record=R.PROGRAMS, status_enum=ProgramStatus,
    subtitle="Programas de lealtad: se crean, otro usuario los aprueba y luego se activan.",
    columns=(C("Código", "code"), C("Nombre", "name"), C("Moneda", "currency_name"),
             C("Estado", "status", "status"), C("Creado", "created_at", "date")),
    actions=(
        A("create_program", "Nuevo programa", LP.PROGRAM_CREATE, variant="primary", fields=(
            F("code", "Código"), F("name", "Nombre"),
            F("currency_name", "Nombre de la moneda", helper="Ej. Puntos SPJ, Estrellas"),
            F("currency_symbol", "Símbolo", required=False),
            F("description", "Descripción", K.MULTILINE, required=False)),
          success="Programa creado y enviado a aprobación."),
        A("approve_program", "Aprobar", LP.PROGRAM_APPROVE, selection_param="program_id",
          confirm="Quien creó el programa no puede aprobarlo.", success="Programa aprobado."),
        A("activate_program", "Activar", LP.PROGRAM_ACTIVATE, selection_param="program_id",
          confirm="El programa empezará a operar.", success="Programa activo."),
        A("suspend_program", "Suspender", LP.PROGRAM_SUSPEND, selection_param="program_id",
          variant="danger", fields=(_MOTIVO,), success="Programa suspendido."),
    ),
    empty_message="Aún no hay programas. Crea el primero con «Nuevo programa».")

# ── Membresías ──────────────────────────────────────────────────────────────
MEMBERSHIPS = P(
    key="memberships", title="Membresías", record=R.MEMBERSHIPS, status_enum=MembershipStatus,
    subtitle="Clientes inscritos en cada programa. La identidad del cliente vive en Clientes.",
    columns=(C("Cliente", "customer_name"), C("Programa", "program_name"),
             C("Nivel", "tier_name"), C("Estado", "status", "status"),
             C("Inscrito", "enrolled_at", "date")),
    actions=(
        A("enroll_membership", "Inscribir cliente", LP.MEMBERSHIP_ENROLL, variant="primary",
          fields=(F("customer_id", "Cliente", K.CUSTOMER), _PROGRAMA),
          success="Cliente inscrito."),
        A("suspend_membership", "Suspender", LP.MEMBERSHIP_SUSPEND,
          selection_param="membership_id", fields=(_MOTIVO,), success="Membresía suspendida."),
        A("close_membership", "Cerrar", LP.MEMBERSHIP_CLOSE, selection_param="membership_id",
          variant="danger", fields=(_MOTIVO,),
          confirm="Cerrar la membresía no borra puntos ni movimientos.",
          success="Membresía cerrada."),
    ),
    empty_message="Nadie inscrito todavía.")

# ── Puntos ──────────────────────────────────────────────────────────────────
POINT_ACCOUNTS = P(
    key="point_accounts", title="Cuentas de puntos", record=R.ACCOUNTS, status_enum=AccountStatus,
    subtitle="Saldo de cada cliente, derivado del libro de movimientos.",
    columns=(C("Cliente", "customer_name"), C("Número", "customer_number"),
             C("Saldo", "points", "numeric"), C("Reservado", "reserved", "numeric"),
             C("Estado", "status", "status"), C("Abierta", "created_at", "date")),
    actions=(
        A("accrue_points", "Acreditar", LP.POINTS_CREDIT, selection_param="loyalty_account_id",
          fields=(F("points_amount", "Puntos", K.DECIMAL),
                  F("reason_code", "Motivo", helper="Queda en el movimiento y en la auditoría.")),
          success="Puntos acreditados."),
        A("redeem_points", "Canjear", LP.POINTS_REDEEM, selection_param="loyalty_account_id",
          fields=(F("points_amount", "Puntos", K.DECIMAL), F("reason_code", "Motivo")),
          success="Puntos canjeados."),
        A("adjust_points", "Ajustar", LP.POINTS_VIEW, selection_param="loyalty_account_id",
          fields=(F("points_amount", "Puntos (positivo suma, negativo resta)", K.DECIMAL),
                  F("reason_code", "Motivo"),
                  F("authorizer_user_id", "Autoriza", K.AUTHORIZER,
                    helper="Otra persona con permiso de ajustar puntos; quien pide no se "
                           "autoriza a sí mismo.")),
          success="Ajuste registrado con autorización."),
    ),
    empty_message="Ningún cliente tiene cuenta de puntos todavía; se abre con su primera compra.")

POINT_LEDGER = P(
    key="point_ledger", title="Movimientos", record=R.LEDGER, status_enum=TransactionType,
    subtitle="El libro de puntos. Nada se edita: toda corrección es un movimiento nuevo.",
    columns=(C("Fecha", "created_at", "date"), C("Cliente", "customer_name"),
             C("Tipo", "transaction_type", "status"), C("Puntos", "points_amount", "numeric"),
             C("Motivo", "reason_code"), C("Origen", "source_module"),
             C("Vence", "expires_at", "date")),
    actions=(
        A("reverse_transaction", "Reversar", LP.POINTS_REVERSE, selection_param="transaction_id",
          variant="danger", fields=(F("reason_code", "Motivo"),),
          success="Movimiento reversado con un movimiento compensatorio."),
    ),
    empty_message="Sin movimientos.")

POINTS = TabbedSpec(key="points", title="Puntos", subtitle="Saldos y libro de movimientos.",
                    tabs=(("Cuentas", POINT_ACCOUNTS), ("Movimientos", POINT_LEDGER)))

# ── Niveles ─────────────────────────────────────────────────────────────────
TIERS = P(
    key="tiers", title="Niveles", record=R.TIERS, status_enum=TierEvaluationMethod,
    subtitle="Niveles de cada programa y sus umbrales. Cada cambio de nivel deja historial.",
    columns=(C("Programa", "program_name"), C("Rango", "rank", "numeric"),
             C("Código", "code"), C("Nombre", "name"),
             C("Puntos mínimos", "minimum_points", "numeric"),
             C("Gasto mínimo", "minimum_spend", "money"),
             C("Visitas mínimas", "minimum_visits", "numeric"),
             C("Evaluación", "evaluation_method", "status"),
             C("Multiplicador", "benefit_multiplier", "numeric"), C("Activo", "active", "bool")),
    actions=(
        A("create_tier", "Nuevo nivel", LP.TIER_MANAGE, variant="primary", fields=(
            _PROGRAMA, F("code", "Código"), F("name", "Nombre"),
            F("rank", "Rango", K.INTEGER, helper="El nivel de entrada es el rango 1."),
            F("minimum_points", "Puntos mínimos", K.DECIMAL, required=False, default="0"),
            F("minimum_spend", "Gasto mínimo", K.MONEY, required=False),
            F("minimum_visits", "Visitas mínimas", K.INTEGER, required=False),
            F("evaluation_method", "Método de evaluación", K.CHOICE,
              enum=TierEvaluationMethod, default="LIFETIME"),
            F("benefit_multiplier", "Multiplicador de puntos", K.DECIMAL, default="1")),
          success="Nivel creado."),
    ),
    empty_message="Sin niveles. Un programa puede operar sin niveles.")

# ── Recompensas ─────────────────────────────────────────────────────────────
REWARD_CATALOG = P(
    key="reward_catalog", title="Catálogo de recompensas", record=R.REWARDS,
    status_enum=RewardType, subtitle="Lo que un miembro puede obtener con sus puntos.",
    columns=(C("Programa", "program_name"), C("Código", "code"), C("Nombre", "name"),
             C("Tipo", "reward_type", "status"), C("Costo en puntos", "points_cost", "numeric"),
             C("Valor", "value", "money"), C("Activa", "active", "bool")),
    actions=(
        A("create_reward", "Nueva recompensa", LP.REWARD_MANAGE, variant="primary", fields=(
            _PROGRAMA, F("code", "Código"), F("name", "Nombre"),
            F("reward_type", "Tipo", K.CHOICE, enum=RewardType),
            F("points_cost", "Costo en puntos", K.DECIMAL),
            F("value", "Valor de referencia", K.MONEY, required=False),
            F("description", "Descripción", K.MULTILINE, required=False)),
          success="Recompensa creada."),
    ),
    empty_message="Sin recompensas en el catálogo.")

REWARD_REDEMPTIONS = P(
    key="reward_redemptions", title="Canjes de recompensas", record=R.REWARD_REDEMPTIONS,
    status_enum=RewardRedemptionStatus,
    subtitle="Un canje reserva los puntos y se confirma al entregar.",
    columns=(C("Solicitado", "requested_at", "date"), C("Cliente", "customer_name"),
             C("Recompensa", "reward_name"), C("Puntos", "points_cost", "numeric"),
             C("Estado", "status", "status"), C("Confirmado", "confirmed_at", "date")),
    actions=(
        A("confirm_reward_redemption", "Confirmar entrega", LP.REWARD_REDEEM,
          selection_param="redemption_id", success="Canje confirmado."),
        A("cancel_reward_redemption", "Cancelar canje", LP.REWARD_REDEEM,
          selection_param="redemption_id", variant="danger",
          confirm="Los puntos reservados vuelven al cliente.", success="Canje cancelado."),
    ),
    empty_message="Sin canjes.")

# ── Retos ───────────────────────────────────────────────────────────────────
CHALLENGES = P(
    key="challenges", title="Retos y misiones", record=R.CHALLENGES, status_enum=ChallengeStatus,
    subtitle="Metas que otorgan puntos al cumplirse; cada otorgamiento es idempotente.",
    columns=(C("Programa", "program_name"), C("Código", "code"), C("Nombre", "name"),
             C("Modo", "mode", "enum", ChallengeMode),
             C("Criterio", "criteria_type", "enum", ChallengeCriteriaType),
             C("Meta", "target_value", "numeric"), C("Puntos", "points_reward", "numeric"),
             C("Estado", "status", "status"), C("Cumplidos", "completed", "numeric")),
    actions=(
        A("create_challenge", "Nuevo reto", LP.CHALLENGE_MANAGE, variant="primary", fields=(
            _PROGRAMA, F("code", "Código"), F("name", "Nombre"),
            F("mode", "Modo", K.CHOICE, enum=ChallengeMode, default="CHALLENGE"),
            F("criteria_type", "Criterio", K.CHOICE, enum=ChallengeCriteriaType),
            F("target_value", "Meta", K.DECIMAL),
            F("points_reward", "Puntos al cumplir", K.DECIMAL),
            F("description", "Descripción", K.MULTILINE, required=False)),
          success="Reto creado."),
        A("activate_challenge", "Activar", LP.CHALLENGE_MANAGE, selection_param="challenge_id",
          success="Reto activo."),
    ),
    empty_message="Sin retos.")

# ── Referidos ───────────────────────────────────────────────────────────────
REFERRALS = P(
    key="referrals", title="Referidos", record=R.REFERRALS, status_enum=ReferralStatus,
    subtitle="Un miembro recomienda a un cliente; el bono se otorga al calificar.",
    columns=(C("Registrado", "registered_at", "date"), C("Quien refiere", "referrer_name"),
             C("Referido", "referred_name"), C("Programa", "program_name"),
             C("Estado", "status", "status"),
             C("Bono de quien refiere", "referrer_bonus_points", "numeric"),
             C("Bono del referido", "referred_bonus_points", "numeric"),
             C("Vence", "expires_at", "date")),
    actions=(
        A("register_referral", "Registrar referido", LP.REFERRAL_MANAGE, variant="primary",
          fields=(_PROGRAMA, F("referrer_membership_id", "Quien refiere", K.RECORD,
                               record=R.MEMBERSHIPS,
                               record_label=("customer_name", "program_name"),
                               record_filters={"status": "ACTIVE"}),
                  F("referred_customer_id", "Cliente referido", K.CUSTOMER),
                  F("referrer_bonus_points", "Bono de quien refiere", K.DECIMAL),
                  F("referred_bonus_points", "Bono del referido", K.DECIMAL, required=False),
                  F("minimum_purchase_amount", "Compra mínima para calificar", K.MONEY,
                    required=False),
                  F("expires_at", "Vence", K.DATE, required=False)),
          success="Referido registrado."),
        A("qualify_referral", "Calificar", LP.REFERRAL_APPROVE, selection_param="referral_id",
          success="Referido calificado."),
        A("reward_referral", "Otorgar bonos", LP.REFERRAL_APPROVE, selection_param="referral_id",
          success="Bonos otorgados."),
        A("reject_referral", "Rechazar", LP.REFERRAL_APPROVE, selection_param="referral_id",
          variant="danger", fields=(_MOTIVO,), success="Referido rechazado."),
        A("flag_referral_fraud", "Sospecha de fraude", LP.REFERRAL_APPROVE,
          selection_param="referral_id", variant="danger", fields=(_MOTIVO,),
          success="Referido marcado como sospechoso."),
    ),
    empty_message="Sin referidos.")

# ── Campañas ────────────────────────────────────────────────────────────────
_CAMPAIGN_COLUMNS = (
    C("Código", "code"), C("Nombre", "name"), C("Tipo", "campaign_type", "enum", CampaignType),
    C("Estado", "status", "status"), C("Inicio", "start_at", "date"), C("Fin", "end_at", "date"),
    C("Presupuesto", "budget_limit", "money"))


def _campaign_actions(only_types: tuple[str, ...] = ()) -> tuple[A, ...]:
    return (
        A("create_campaign", "Nueva campaña", LP.CAMPAIGN_CREATE, variant="primary", fields=(
            _PROGRAMA, F("code", "Código"), F("name", "Nombre"),
            F("campaign_type", "Tipo", K.CHOICE, enum=CampaignType, only=only_types),
            F("start_at", "Inicio", K.DATE, required=False),
            F("end_at", "Fin", K.DATE, required=False),
            F("budget_limit", "Presupuesto", K.MONEY, required=False),
            F("benefit_type", "Beneficio", required=False,
              helper="Puntos, cupón o vale que otorga la campaña."),
            F("audience_definition", "Audiencia", K.MULTILINE, required=False,
              helper="Segmento que publica Inteligencia; Fidelidad no calcula churn.")),
          success="Campaña creada y enviada a aprobación."),
        A("approve_campaign", "Aprobar", LP.CAMPAIGN_APPROVE, selection_param="campaign_id",
          confirm="Quien creó la campaña no puede aprobarla.", success="Campaña aprobada."),
        A("schedule_campaign", "Programar", LP.CAMPAIGN_ACTIVATE, selection_param="campaign_id",
          success="Campaña programada."),
        A("activate_campaign", "Activar", LP.CAMPAIGN_ACTIVATE, selection_param="campaign_id",
          success="Campaña activa."),
        A("pause_campaign", "Pausar", LP.CAMPAIGN_ACTIVATE, selection_param="campaign_id",
          success="Campaña en pausa."),
        A("complete_campaign", "Concluir", LP.CAMPAIGN_ACTIVATE, selection_param="campaign_id",
          success="Campaña concluida."),
        A("cancel_campaign", "Cancelar", LP.CAMPAIGN_ACTIVATE, selection_param="campaign_id",
          variant="danger", fields=(_MOTIVO,), success="Campaña cancelada."),
    )


CAMPAIGNS = P(
    key="campaigns", title="Campañas", record=R.CAMPAIGNS, status_enum=CampaignStatus,
    subtitle="Campañas con presupuesto, vigencia y aprobación de otra persona.",
    columns=_CAMPAIGN_COLUMNS, actions=_campaign_actions(), empty_message="Sin campañas.")

RETENTION = P(
    key="retention", title="Retención", record=R.RETENTION_CAMPAIGNS, status_enum=CampaignStatus,
    subtitle="Campañas de retención y recuperación sobre segmentos que publica Inteligencia.",
    columns=_CAMPAIGN_COLUMNS, actions=_campaign_actions(("RETENTION", "WIN_BACK")),
    empty_message="Sin campañas de retención.")

# ── Cumpleaños ──────────────────────────────────────────────────────────────
BIRTHDAYS = P(
    key="birthdays", title="Cumpleaños", record=R.BIRTHDAYS, status_enum=BirthdayBenefitType,
    subtitle="Beneficio de cumpleaños por programa. Sólo se envía con consentimiento.",
    columns=(C("Programa", "program_name"), C("Activo", "enabled", "bool"),
             C("Beneficio", "benefit_type", "status"), C("Puntos", "points_amount", "numeric"),
             C("Días antes", "days_before", "numeric"), C("Días después", "days_after", "numeric"),
             C("Canal", "notification_channel")),
    actions=(
        A("configure_birthday", "Configurar", LP.BIRTHDAY_MANAGE, variant="primary", fields=(
            _PROGRAMA, F("enabled", "Activo", K.BOOL, required=False, default=True),
            F("benefit_type", "Beneficio", K.CHOICE, enum=BirthdayBenefitType, default="POINTS"),
            F("points_amount", "Puntos", K.DECIMAL, required=False, default="0"),
            F("days_before", "Días antes", K.INTEGER, required=False),
            F("days_after", "Días después", K.INTEGER, required=False),
            F("notification_channel", "Canal de aviso", required=False)),
          success="Beneficio de cumpleaños guardado."),
    ),
    empty_message="Sin beneficio de cumpleaños configurado.")

# ── Cupones y vales ─────────────────────────────────────────────────────────
COUPON_DEFINITIONS = P(
    key="coupon_definitions", title="Definiciones de cupón", record=R.COUPON_DEFINITIONS,
    status_enum=CouponType, subtitle="Qué otorga cada cupón y su vigencia.",
    columns=(C("Código", "code"), C("Nombre", "name"), C("Tipo", "coupon_type", "status"),
             C("Beneficio", "benefit_type", "enum", CommercialBenefitType),
             C("Valor", "benefit_value", "numeric"), C("Desde", "valid_from", "date"),
             C("Hasta", "valid_to", "date"), C("Emitidos", "issued", "numeric"),
             C("Activa", "active", "bool")),
    actions=(
        A("create_coupon_definition", "Nueva definición", LP.COUPON_ISSUE, variant="primary",
          fields=(F("code", "Código"), F("name", "Nombre"),
                  F("coupon_type", "Tipo", K.CHOICE, enum=CouponType),
                  F("benefit_type", "Beneficio", K.CHOICE, enum=CommercialBenefitType),
                  F("benefit_value", "Valor del beneficio", K.DECIMAL),
                  F("valid_from", "Desde", K.DATE, required=False),
                  F("valid_to", "Hasta", K.DATE, required=False)),
          success="Definición creada."),
    ),
    empty_message="Sin definiciones de cupón.")

COUPONS = P(
    key="coupons", title="Cupones emitidos", record=R.COUPONS, status_enum=CouponInstanceStatus,
    subtitle="Un cupón se reserva en la venta y se confirma sólo al completarla.",
    columns=(C("Código", "code"), C("Definición", "definition_name"),
             C("Cliente", "customer_name"), C("Estado", "status", "status"),
             C("Emitido", "issued_at", "date"), C("Canjeado", "redeemed_at", "date")),
    actions=(
        A("issue_coupon", "Emitir cupón", LP.COUPON_ISSUE, variant="primary", fields=(
            F("definition_id", "Definición", K.RECORD, record=R.COUPON_DEFINITIONS,
              record_label=("name", "code")),
            F("customer_id", "Cliente", K.CUSTOMER, required=False,
              helper="Vacío = cupón al portador.")),
          success="Cupón emitido."),
        A("cancel_coupon", "Cancelar", LP.COUPON_CANCEL, selection_param="coupon_instance_id",
          variant="danger", fields=(_MOTIVO,), success="Cupón cancelado."),
    ),
    empty_message="Sin cupones emitidos.")

COUPONS_TABS = TabbedSpec(key="coupons", title="Cupones", subtitle="Definiciones y cupones emitidos.",
                          tabs=(("Emitidos", COUPONS), ("Definiciones", COUPON_DEFINITIONS)))

VOUCHER_DEFINITIONS = P(
    key="voucher_definitions", title="Tipos de vale", record=R.VOUCHER_DEFINITIONS,
    status_enum=VoucherType, subtitle="Cada tipo de vale y su naturaleza (saldo a favor, promocional…).",
    columns=(C("Código", "code"), C("Nombre", "name"), C("Tipo", "voucher_type", "status"),
             C("Emitidos", "issued", "numeric"), C("Activo", "active", "bool")),
    actions=(
        A("create_voucher_definition", "Nuevo tipo de vale", LP.VOUCHER_ISSUE, variant="primary",
          fields=(F("code", "Código"), F("name", "Nombre"),
                  F("voucher_type", "Tipo", K.CHOICE, enum=VoucherType)),
          success="Tipo de vale creado."),
    ),
    empty_message="Sin tipos de vale.")

VOUCHERS = P(
    key="vouchers", title="Vales emitidos", record=R.VOUCHERS, status_enum=VoucherInstanceStatus,
    subtitle="Saldo de cada vale derivado de su libro; admite canje parcial.",
    columns=(C("Código", "code"), C("Tipo", "definition_name"), C("Cliente", "customer_name"),
             C("Saldo", "balance", "money"), C("Estado", "status", "status"),
             C("Emitido", "issued_at", "date"), C("Vence", "expires_at", "date")),
    actions=(
        A("issue_voucher", "Emitir vale", LP.VOUCHER_ISSUE, variant="primary", fields=(
            F("definition_id", "Tipo de vale", K.RECORD, record=R.VOUCHER_DEFINITIONS,
              record_label=("name", "code")),
            F("customer_id", "Cliente", K.CUSTOMER, required=False),
            F("amount", "Monto", K.MONEY), F("expires_at", "Vence", K.DATE, required=False)),
          success="Vale emitido."),
    ),
    empty_message="Sin vales emitidos.")

VOUCHERS_TABS = TabbedSpec(key="vouchers", title="Vales", subtitle="Tipos de vale y vales emitidos.",
                           tabs=(("Emitidos", VOUCHERS), ("Tipos", VOUCHER_DEFINITIONS)))

# ── Sorteos ─────────────────────────────────────────────────────────────────
_CAMPANA_SORTEO = F("campaign_id", "Campaña de sorteo", K.RECORD, record=R.SWEEPSTAKES_CAMPAIGNS,
                    record_label=("name", "code"))

SWEEPSTAKES_CAMPAIGNS = P(
    key="sweepstakes_campaigns", title="Campañas de sorteo", record=R.SWEEPSTAKES_CAMPAIGNS,
    status_enum=SweepstakesCampaignStatus,
    subtitle="Reglas de participación, premios y vigencia. Las aprueba otra persona.",
    columns=(C("Código", "code"), C("Nombre", "name"), C("Estado", "status", "status"),
             C("Inicio", "starts_at", "date"), C("Fin", "ends_at", "date"),
             C("Participaciones", "entries", "numeric"), C("Boletos", "tickets", "numeric"),
             C("Premios", "prizes", "numeric")),
    actions=(
        A("create_sweepstakes_campaign", "Nueva campaña", LP.SWEEPSTAKES_MANAGE,
          variant="primary", fields=(
              F("code", "Código"), F("name", "Nombre"),
              F("description", "Descripción", K.MULTILINE, required=False),
              F("starts_at", "Inicio", K.DATE, required=False),
              F("ends_at", "Fin", K.DATE, required=False)),
          success="Campaña creada."),
        A("approve_sweepstakes_campaign", "Aprobar", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", success="Campaña aprobada."),
        A("activate_sweepstakes_campaign", "Activar", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", success="Campaña activa."),
        A("pause_sweepstakes_campaign", "Pausar", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", success="Campaña en pausa."),
        A("resume_sweepstakes_campaign", "Reanudar", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", success="Campaña reanudada."),
        A("close_sweepstakes_campaign", "Cerrar", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", success="Campaña cerrada."),
        A("cancel_sweepstakes_campaign", "Cancelar", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", variant="danger",
          confirm="Cancelar una campaña no borra sus participaciones.",
          success="Campaña cancelada."),
        A("configure_sweepstakes_rule", "Regla de participación", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", fields=(
              F("entry_method", "Forma de participar", K.CHOICE, enum=SweepstakesEntryMethod),
              F("amount_per_ticket", "Monto por boleto", K.MONEY, required=False),
              F("tickets_per_sale", "Boletos por venta", K.INTEGER, required=False),
              F("max_tickets_per_sale", "Máximo por venta", K.INTEGER, required=False),
              F("max_tickets_per_customer", "Máximo por cliente", K.INTEGER, required=False),
              F("requires_registered_customer", "Exige cliente identificado", K.BOOL,
                required=False, default=True)),
          success="Regla guardada."),
        A("add_sweepstakes_prize", "Agregar premio", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", fields=(
              F("name", "Premio"), F("rank", "Lugar", K.INTEGER),
              F("quantity", "Cantidad", K.INTEGER),
              F("estimated_cost", "Costo estimado", K.MONEY, required=False),
              F("description", "Descripción", K.MULTILINE, required=False)),
          success="Premio agregado."),
        A("grant_sweepstakes_entry", "Otorgar participación", LP.SWEEPSTAKES_MANAGE,
          selection_param="campaign_id", fields=(
              F("customer_id", "Cliente", K.CUSTOMER),
              F("chances_granted", "Oportunidades", K.INTEGER),
              F("notes", "Motivo", K.MULTILINE)),
          fixed={"entry_method": SweepstakesEntryMethod.MANUAL_GRANT},
          success="Participación otorgada; emite su boleto en «Participaciones»."),
    ),
    empty_message="Sin campañas de sorteo.")

SWEEPSTAKES_ENTRIES = P(
    key="sweepstakes_entries", title="Participaciones", record=R.SWEEPSTAKES_ENTRIES,
    status_enum=SweepstakesEntryMethod,
    subtitle="La participación existe ANTES que el boleto; el boleto existe antes de imprimirse.",
    columns=(C("Fecha", "created_at", "date"), C("Campaña", "campaign_name"),
             C("Cliente", "customer_name"), C("Forma", "entry_method", "status"),
             C("Oportunidades", "chances_granted", "numeric"), C("Boletos", "tickets", "numeric")),
    actions=(
        A("issue_sweepstakes_ticket", "Emitir boleto", LP.SWEEPSTAKES_TICKET_PRINT,
          selection_param="entry_id", selection_extra={"campaign_id": "campaign_id"},
          success="Boleto emitido."),
    ),
    empty_message="Sin participaciones.")

SWEEPSTAKES_TICKETS = P(
    key="sweepstakes_tickets", title="Boletos", record=R.SWEEPSTAKES_TICKETS,
    status_enum=SweepstakesTicketStatus,
    subtitle="Reimprimir conserva el folio y no crea otra participación.",
    columns=(C("Folio", "ticket_number"), C("Campaña", "campaign_name"),
             C("Cliente", "customer_name"), C("Estado", "status", "status"),
             C("Impresiones", "print_count", "numeric"),
             C("Última impresión", "last_printed_at", "date")),
    actions=(
        A("print_sweepstakes_ticket", "Imprimir", LP.SWEEPSTAKES_TICKET_PRINT,
          selection_param="ticket_id", success="Boleto enviado a impresión."),
        A("print_sweepstakes_ticket", "Reimprimir", LP.SWEEPSTAKES_TICKET_REPRINT,
          selection_param="ticket_id", fields=(_MOTIVO,),
          success="Reimpresión registrada (mismo folio, marcada como copia)."),
        A("void_sweepstakes_ticket", "Anular", LP.SWEEPSTAKES_MANAGE, selection_param="ticket_id",
          variant="danger", fields=(_MOTIVO,), success="Boleto anulado."),
    ),
    empty_message="Sin boletos.")

SWEEPSTAKES_PRIZES = P(
    key="sweepstakes_prizes", title="Premios", record=R.SWEEPSTAKES_PRIZES,
    status_enum=SweepstakesPrizeStatus, subtitle="Premios por lugar de cada campaña.",
    columns=(C("Campaña", "campaign_name"), C("Lugar", "rank", "numeric"), C("Premio", "name"),
             C("Cantidad", "quantity", "numeric"), C("Costo estimado", "estimated_cost", "money"),
             C("Estado", "status", "status")),
    empty_message="Sin premios.")

SWEEPSTAKES_TABS = TabbedSpec(
    key="sweepstakes", title="Campañas de sorteo", subtitle="Campañas, participaciones, boletos y premios.",
    tabs=(("Campañas", SWEEPSTAKES_CAMPAIGNS), ("Participaciones", SWEEPSTAKES_ENTRIES),
          ("Boletos", SWEEPSTAKES_TICKETS), ("Premios", SWEEPSTAKES_PRIZES)))

SWEEPSTAKES_DRAWS = P(
    key="sweepstakes_draws", title="Sorteos", record=R.SWEEPSTAKES_DRAWS,
    status_enum=SweepstakesDrawStatus,
    subtitle="Cada sorteo guarda semilla, huella de la tómbola y número de boletos elegibles.",
    columns=(C("Campaña", "campaign_name"), C("Estado", "status", "status"),
             C("Programado", "scheduled_at", "date"), C("Realizado", "executed_at", "date"),
             C("Boletos elegibles", "ticket_pool_size", "numeric"), C("Semilla", "random_seed")),
    actions=(
        A("schedule_sweepstakes_draw", "Programar sorteo", LP.SWEEPSTAKES_DRAW,
          variant="primary", fields=(_CAMPANA_SORTEO,
                                     F("scheduled_at", "Fecha", K.DATE, required=False)),
          success="Sorteo programado."),
        A("execute_sweepstakes_draw", "Ejecutar sorteo", LP.SWEEPSTAKES_DRAW,
          selection_param="draw_id",
          confirm="Se elige al azar entre los boletos elegibles y queda registrado. No se puede repetir.",
          success="Sorteo realizado."),
        A("cancel_sweepstakes_draw", "Cancelar", LP.SWEEPSTAKES_DRAW, selection_param="draw_id",
          variant="danger", confirm="El sorteo programado se cancela.",
          success="Sorteo cancelado."),
    ),
    empty_message="Sin sorteos programados.")

SWEEPSTAKES_WINNERS = P(
    key="sweepstakes_winners", title="Ganadores", record=R.SWEEPSTAKES_WINNERS,
    status_enum=SweepstakesWinnerStatus,
    subtitle="Validar, descalificar y entregar premios; nada se elige a mano.",
    columns=(C("Seleccionado", "selected_at", "date"), C("Campaña", "campaign_name"),
             C("Folio", "ticket_number"), C("Cliente", "customer_name"),
             C("Premio", "prize_name"), C("Lugar", "rank", "numeric"),
             C("Estado", "status", "status"), C("Entregado", "delivered_at", "date")),
    actions=(
        A("validate_sweepstakes_winner", "Validar", LP.SWEEPSTAKES_DRAW,
          selection_param="winner_id", success="Ganador validado."),
        A("disqualify_sweepstakes_winner", "Descalificar", LP.SWEEPSTAKES_DRAW,
          selection_param="winner_id", variant="danger", fields=(_MOTIVO,),
          success="Ganador descalificado."),
        A("deliver_sweepstakes_prize", "Entregar premio", LP.SWEEPSTAKES_DRAW,
          selection_param="winner_id", success="Premio entregado."),
    ),
    empty_message="Sin ganadores todavía.")

DRAWS_TABS = TabbedSpec(key="draws", title="Sorteo y ganadores",
                        subtitle="Ejecución auditable del sorteo y validación de ganadores.",
                        tabs=(("Sorteos", SWEEPSTAKES_DRAWS), ("Ganadores", SWEEPSTAKES_WINNERS)))

# ── Control ─────────────────────────────────────────────────────────────────
FRAUD = P(
    key="fraud", title="Antifraude", record=R.FRAUD_CASES, status_enum=FraudCaseStatus,
    subtitle="Casos abiertos sobre referidos, movimientos, cupones, vales o participaciones.",
    columns=(C("Abierto", "opened_at", "date"),
             C("Sobre", "subject_type", "enum", FraudCaseSubjectType),
             C("Cliente", "customer_name"), C("Motivo", "reason"),
             C("Estado", "status", "status"), C("Resuelto", "resolved_at", "date")),
    actions=(
        A("open_fraud_case", "Abrir caso", LP.FRAUD_MANAGE, variant="primary", fields=(
            F("subject_type", "Sobre qué", K.CHOICE, enum=FraudCaseSubjectType),
            F("subject_id", "Folio o referencia del registro"),
            F("customer_id", "Cliente", K.CUSTOMER), _MOTIVO),
          success="Caso abierto."),
        A("start_fraud_review", "Iniciar revisión", LP.FRAUD_MANAGE, selection_param="case_id",
          success="Caso en revisión."),
        A("confirm_fraud_case", "Confirmar", LP.FRAUD_MANAGE, selection_param="case_id",
          variant="danger", fields=(F("resolution_notes", "Resolución", K.MULTILINE),),
          confirm="Quien abrió el caso no puede resolverlo.", success="Fraude confirmado."),
        A("dismiss_fraud_case", "Descartar", LP.FRAUD_MANAGE, selection_param="case_id",
          fields=(F("resolution_notes", "Resolución", K.MULTILINE),), success="Caso descartado."),
    ),
    empty_message="Sin casos de fraude.")

AUDIT = P(
    key="audit", title="Auditoría", record=R.LOYALTY_AUDIT,
    subtitle="Quién emitió, ajustó, canjeó, aprobó o sorteó cada cosa, y cuándo.",
    columns=(C("Fecha", "fecha", "date"), C("Usuario", "usuario"), C("Acción", "accion"),
             C("Entidad", "entidad"), C("Referencia", "entidad_id")),
    empty_message="Sin registros de auditoría.")

ACCOUNTING = P(
    key="accounting", title="Contabilidad", record=R.FINANCE_POSTINGS,
    status_enum=LoyaltyFinancePostingStatus,
    subtitle=("Asiento contable de puntos, vales, cupones y premios de sorteo. Lo que falla "
              "(sin perfil contable, periodo cerrado) se reintenta solo en cada operación."),
    columns=(C("Fecha", "updated_at", "date"),
             C("Origen", "source_type", "enum", LoyaltyFinanceSourceType),
             C("Referencia", "source_id"), C("Importe", "amount", "money"),
             C("Estado", "status", "status"), C("Detalle", "detail"),
             C("Intentos", "attempts", "numeric")),
    actions=(
        A("post_loyalty_finance", "Contabilizar pendientes", LP.AUDIT_VIEW, variant="primary",
          success="Pendientes procesados."),
    ),
    empty_message="Aún no hay movimientos de fidelidad contabilizados.")

#: route_id → especificación (página simple o con pestañas).
FIDELIDAD_RECORD_ROUTES: dict[str, P | TabbedSpec] = {
    "loyalty.programs": PROGRAMS,
    "loyalty.memberships": MEMBERSHIPS,
    "loyalty.points": POINTS,
    "loyalty.tiers": TIERS,
    "loyalty.challenges": CHALLENGES,
    "loyalty.referrals": REFERRALS,
    "loyalty.campaigns": CAMPAIGNS,
    "loyalty.birthdays": BIRTHDAYS,
    "loyalty.retention": RETENTION,
    "instruments.coupons": COUPONS_TABS,
    "instruments.vouchers": VOUCHERS_TABS,
    "sweepstakes.campaigns": SWEEPSTAKES_TABS,
    "sweepstakes.draws": DRAWS_TABS,
    "fidelidad.fraud": FRAUD,
    "fidelidad.audit": AUDIT,
    "fidelidad.accounting": ACCOUNTING,
}

__all__ = ["FIDELIDAD_RECORD_ROUTES", "REWARD_CATALOG", "REWARD_REDEMPTIONS"]
