"""Navigation model for the Fidelidad desktop workspace (LOY-25).

Mirrors ``frontend/desktop/modules/customers_crm/customers_crm_routes.py``'s
shape (route dataclass + ``visible_routes``/``grouped_routes``). Every
route the master prompt's own §6 sidebar envisions for Fidelidad is
declared here up front, even though only a handful have a real page today
— ``fidelidad_workspace.py`` resolves any route without a built page to
the canonical ``ViewState.EMPTY`` placeholder, never to ``None``, the same
incremental-build convention ``customers_crm`` and ``orders_delivery``
already established (each later phase adds the page for one more route).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.loyalty.permissions import LoyaltyPermissions
from frontend.desktop.modules.fidelidad.view_models import FidelidadCapabilities


@dataclass(frozen=True)
class FidelidadRoute:
    route_id: str
    label: str
    group: str
    tooltip: str
    required_permission: str
    capability: str


FIDELIDAD_ROUTES: tuple[FidelidadRoute, ...] = (
    # -- Resumen --------------------------------------------------------
    FidelidadRoute(
        route_id="fidelidad.overview", label="Resumen", group="Resumen",
        tooltip="Estado general del programa de fidelidad.",
        required_permission=LoyaltyPermissions.VIEW, capability="module_view"),

    # -- Programas --------------------------------------------------------
    FidelidadRoute(
        route_id="loyalty.programs", label="Programas", group="Programas",
        tooltip="Programas de fidelidad activos.",
        required_permission=LoyaltyPermissions.PROGRAM_VIEW, capability="programs"),

    # -- Miembros ---------------------------------------------------------
    FidelidadRoute(
        route_id="loyalty.member_profile", label="Perfil de miembro", group="Miembros",
        tooltip="Cuenta, membresías, saldo de puntos y movimientos de un cliente.",
        required_permission=LoyaltyPermissions.MEMBERSHIP_VIEW, capability="members"),
    FidelidadRoute(
        route_id="loyalty.tiers", label="Niveles", group="Miembros",
        tooltip="Niveles de membresía del programa.",
        required_permission=LoyaltyPermissions.TIER_VIEW, capability="members"),

    # -- Recompensas y retos ------------------------------------------------
    FidelidadRoute(
        route_id="loyalty.rewards", label="Recompensas", group="Recompensas y retos",
        tooltip="Catálogo de recompensas y canje.",
        required_permission=LoyaltyPermissions.REWARD_VIEW, capability="rewards"),
    FidelidadRoute(
        route_id="loyalty.challenges", label="Retos", group="Recompensas y retos",
        tooltip="Retos, misiones y metas.",
        required_permission=LoyaltyPermissions.CHALLENGE_VIEW, capability="challenges"),

    # -- Referidos y ciclo de vida -------------------------------------------
    FidelidadRoute(
        route_id="loyalty.referrals", label="Referidos", group="Referidos y ciclo de vida",
        tooltip="Programa de referidos.",
        required_permission=LoyaltyPermissions.REFERRAL_VIEW, capability="referrals"),
    FidelidadRoute(
        route_id="loyalty.birthdays", label="Cumpleaños", group="Referidos y ciclo de vida",
        tooltip="Configuración de beneficios de cumpleaños.",
        required_permission=LoyaltyPermissions.BIRTHDAY_VIEW, capability="birthdays"),
    FidelidadRoute(
        route_id="loyalty.campaigns", label="Campañas", group="Referidos y ciclo de vida",
        tooltip="Campañas de retención y win-back.",
        required_permission=LoyaltyPermissions.CAMPAIGN_VIEW, capability="campaigns"),

    # -- Instrumentos comerciales --------------------------------------------
    FidelidadRoute(
        route_id="instruments.coupons", label="Cupones", group="Instrumentos comerciales",
        tooltip="Emisión y canje de cupones.",
        required_permission=LoyaltyPermissions.COUPON_VIEW, capability="coupons"),
    FidelidadRoute(
        route_id="instruments.vouchers", label="Vales", group="Instrumentos comerciales",
        tooltip="Emisión y canje de vales.",
        required_permission=LoyaltyPermissions.VOUCHER_VIEW, capability="vouchers"),

    # -- Sorteos ------------------------------------------------------------
    FidelidadRoute(
        route_id="sweepstakes.campaigns", label="Campañas de sorteo", group="Sorteos",
        tooltip="Campañas, reglas, premios y derechos de sorteo.",
        required_permission=LoyaltyPermissions.SWEEPSTAKES_VIEW, capability="sweepstakes"),
    FidelidadRoute(
        route_id="sweepstakes.draws", label="Sorteo y ganadores", group="Sorteos",
        tooltip="Ejecución del sorteo y validación de ganadores.",
        required_permission=LoyaltyPermissions.SWEEPSTAKES_VIEW, capability="sweepstakes"),

    # -- Control -------------------------------------------------------------
    FidelidadRoute(
        route_id="fidelidad.fraud", label="Antifraude", group="Control",
        tooltip="Casos de fraude y revisión.",
        required_permission=LoyaltyPermissions.FRAUD_VIEW, capability="fraud"),
    FidelidadRoute(
        route_id="fidelidad.settings", label="Configuración", group="Control",
        tooltip="Configuración general del módulo.",
        required_permission=LoyaltyPermissions.CONFIG_VIEW, capability="settings"),
)


def visible_routes(capabilities: FidelidadCapabilities) -> tuple[FidelidadRoute, ...]:
    """Return routes authorized by UI capabilities, not raw route permissions."""
    if not capabilities.module_view:
        return ()
    return tuple(
        route for route in FIDELIDAD_ROUTES
        if bool(getattr(capabilities, route.capability, False)))


def grouped_routes(
    routes: tuple[FidelidadRoute, ...] | list[FidelidadRoute] | None = None,
) -> list[tuple[str, list[FidelidadRoute]]]:
    groups: list[tuple[str, list[FidelidadRoute]]] = []
    for route in FIDELIDAD_ROUTES if routes is None else routes:
        if not groups or groups[-1][0] != route.group:
            groups.append((route.group, []))
        groups[-1][1].append(route)
    return groups
