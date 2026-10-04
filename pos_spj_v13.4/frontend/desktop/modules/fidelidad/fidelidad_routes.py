"""Navigation model for the Fidelidad desktop workspace (LOY-25, LOY-29).

The sidebar the master prompt asks for (§6), including the Loyalty Cards
sub-domain as its own group INSIDE Fidelidad (§5: no separate global entry).
Every route is visible only if the session holds that route's own granular
read permission — the coarse per-group flags of LOY-25 hid nothing a user
could not open and showed routes a user could not use.

LOY-29 removed every "en construcción" placeholder: a route is declared here
only if it has a real page behind it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.application.loyalty.permissions import LoyaltyPermissions as LP
from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions as CP
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.fidelidad.view_models import FidelidadCapabilities


@dataclass(frozen=True)
class FidelidadRoute:
    route_id: str
    label: str
    group: str
    tooltip: str
    required_permission: str
    capability: str
    icon: str


GROUP_ICONS: dict[str, str] = {
    "Resumen": Icons.DASHBOARD,
    "Programas": Icons.LOYALTY,
    "Miembros": Icons.CUSTOMERS,
    "Beneficios": Icons.GRADE,
    "Campañas": Icons.RECOVERY,
    "Instrumentos comerciales": Icons.PRICE,
    "Sorteos": Icons.FLAG,
    "Tarjetas de fidelidad": Icons.LOYALTY_CARDS,
    "Control": Icons.AUDIT,
}


def _r(route_id, label, group, tooltip, permission, capability, icon) -> FidelidadRoute:
    return FidelidadRoute(route_id=route_id, label=label, group=group, tooltip=tooltip,
                          required_permission=permission, capability=capability, icon=icon)


FIDELIDAD_ROUTES: tuple[FidelidadRoute, ...] = (
    _r("fidelidad.overview", "Resumen", "Resumen", "Indicadores del programa de lealtad.",
       LP.VIEW, "module_view", Icons.DASHBOARD),
    _r("fidelidad.alerts", "Alertas", "Resumen", "Lo que espera aprobación o atención.",
       LP.DASHBOARD_VIEW, "alerts", Icons.WARNING),

    _r("loyalty.programs", "Programas", "Programas", "Programas de lealtad y su aprobación.",
       LP.PROGRAM_VIEW, "programs", Icons.LOYALTY),
    _r("loyalty.tiers", "Niveles", "Programas", "Niveles y umbrales de cada programa.",
       LP.TIER_VIEW, "members", Icons.GRADE),
    _r("loyalty.rules", "Reglas de acumulación", "Programas",
       "Cuántos puntos da cada compra; el POS las aplica al cobrar.", LP.PROGRAM_VIEW,
       "programs", Icons.CHECKLIST),

    _r("loyalty.memberships", "Membresías", "Miembros", "Clientes inscritos en cada programa.",
       LP.MEMBERSHIP_VIEW, "members", Icons.CHECKLIST),
    _r("loyalty.member_profile", "Perfil de miembro", "Miembros",
       "Cuenta, saldo y movimientos de un cliente.", LP.MEMBERSHIP_VIEW, "members", Icons.USER),
    _r("loyalty.points", "Puntos", "Miembros", "Saldos y libro de movimientos de puntos.",
       LP.POINTS_VIEW, "points", Icons.PRICE),

    _r("loyalty.rewards", "Recompensas", "Beneficios", "Catálogo, canje y entregas.",
       LP.REWARD_VIEW, "rewards", Icons.PACKAGE),
    _r("loyalty.challenges", "Retos y misiones", "Beneficios", "Metas que otorgan puntos.",
       LP.CHALLENGE_VIEW, "challenges", Icons.FLAG),
    _r("loyalty.referrals", "Referidos", "Beneficios", "Programa de referidos.",
       LP.REFERRAL_VIEW, "referrals", Icons.SCENARIO),
    _r("loyalty.birthdays", "Cumpleaños", "Beneficios", "Beneficio de cumpleaños.",
       LP.BIRTHDAY_VIEW, "birthdays", Icons.CALENDAR),

    _r("loyalty.campaigns", "Campañas", "Campañas", "Campañas con presupuesto y aprobación.",
       LP.CAMPAIGN_VIEW, "campaigns", Icons.RECOVERY),
    _r("loyalty.retention", "Retención", "Campañas", "Retención y recuperación de clientes.",
       LP.RETENTION_VIEW, "retention", Icons.RETURN),

    _r("instruments.coupons", "Cupones", "Instrumentos comerciales", "Definición y emisión de cupones.",
       LP.COUPON_VIEW, "coupons", Icons.PRICE),
    _r("instruments.vouchers", "Vales", "Instrumentos comerciales", "Vales con saldo y canje parcial.",
       LP.VOUCHER_VIEW, "vouchers", Icons.DOCUMENT),

    _r("sweepstakes.campaigns", "Campañas de sorteo", "Sorteos",
       "Campañas, participaciones, boletos y premios.", LP.SWEEPSTAKES_VIEW, "sweepstakes",
       Icons.SCHEDULE),
    _r("sweepstakes.draws", "Sorteo y ganadores", "Sorteos", "Sorteo auditable y ganadores.",
       LP.SWEEPSTAKES_VIEW, "sweepstakes", Icons.SUCCESS),

    _r("cards.overview", "Resumen de tarjetas", "Tarjetas de fidelidad",
       "Tarjetas emitidas, activas, bloqueadas y producción.", CP.VIEW, "cards", Icons.DASHBOARD),
    _r("cards.cards", "Tarjetas", "Tarjetas de fidelidad",
       "Emitir, activar, bloquear, reponer y rotar QR.", CP.CARD_VIEW, "cards",
       Icons.LOYALTY_CARDS),
    _r("cards.assignments", "Asignaciones", "Tarjetas de fidelidad",
       "Tarjetas preimpresas entregadas a clientes.", CP.CARD_VIEW, "cards", Icons.USERS),
    _r("cards.templates", "Plantillas", "Tarjetas de fidelidad",
       "Plantillas versionadas y su aprobación.", CP.TEMPLATE_VIEW, "card_templates",
       Icons.DOCUMENT),
    _r("cards.designer", "Diseñador", "Tarjetas de fidelidad",
       "Diseño declarativo de anverso y reverso, con vista previa.", CP.DESIGNER_ACCESS,
       "card_designer", Icons.EDIT),
    _r("cards.sheets", "Formatos y pliegos", "Tarjetas de fidelidad",
       "Pliegos (12 × 18 pulgadas y personalizados) e imposición.", CP.VIEW, "cards",
       Icons.LIST),
    _r("cards.batches", "Lotes", "Tarjetas de fidelidad", "Lotes de tarjetas y su aprobación.",
       CP.VIEW, "cards", Icons.LOTS),
    _r("cards.printing", "Impresión", "Tarjetas de fidelidad",
       "Trabajos de impresión de lotes.", CP.VIEW, "cards", Icons.PRINT),
    _r("cards.reprints", "Reimpresiones", "Tarjetas de fidelidad",
       "Reimpresiones con motivo; no crean tarjetas ni QR nuevos.", CP.VIEW, "cards",
       Icons.REDO),
    _r("cards.digital", "Tarjetas digitales", "Tarjetas de fidelidad",
       "Proyección digital de cada tarjeta.", CP.CARD_VIEW, "cards", Icons.DEVICE),
    _r("cards.qr", "QR y validación", "Tarjetas de fidelidad",
       "Validar el QR de una tarjeta como lo haría el punto de venta.", CP.CARD_VIEW, "cards",
       Icons.SEARCH),
    _r("cards.audit", "Auditoría de tarjetas", "Tarjetas de fidelidad",
       "Emisión, bloqueo, reposición, impresión y rotación de QR.", CP.AUDIT_VIEW, "cards",
       Icons.AUDIT),
    _r("cards.settings", "Configuración de tarjetas", "Tarjetas de fidelidad",
       "Privacidad de lo impreso: nombre y puntos.", CP.CONFIG_VIEW, "cards", Icons.SETTINGS),

    _r("fidelidad.fraud", "Antifraude", "Control", "Casos de fraude y revisión.",
       LP.FRAUD_VIEW, "fraud", Icons.INVESTIGATION),
    _r("fidelidad.audit", "Auditoría", "Control", "Rastro de auditoría de Fidelidad.",
       LP.AUDIT_VIEW, "audit", Icons.AUDIT),
    _r("fidelidad.accounting", "Contabilidad", "Control",
       "Asientos de puntos, vales, cupones y premios; lo que falló y por qué.",
       LP.AUDIT_VIEW, "audit", Icons.FINANCE),
    _r("fidelidad.stacking", "Combinación de beneficios", "Control",
       "Puntos, cupones, vales y promociones en la misma venta.", LP.CONFIG_VIEW, "settings",
       Icons.LIST),
    _r("fidelidad.settings", "Configuración", "Control",
       "Reglas de acumulación, canje y caducidad.", LP.CONFIG_VIEW, "settings", Icons.SETTINGS),
)


def visible_routes(capabilities: FidelidadCapabilities,
                   can: Callable[[str], bool] | None = None) -> tuple[FidelidadRoute, ...]:
    """Routes the session may open: module access + that route's own permission."""
    if not capabilities.module_view:
        return ()
    if can is None:
        return tuple(r for r in FIDELIDAD_ROUTES if bool(getattr(capabilities, r.capability, False)))
    return tuple(r for r in FIDELIDAD_ROUTES if can(r.required_permission))


def grouped_routes(
    routes: tuple[FidelidadRoute, ...] | list[FidelidadRoute] | None = None,
) -> list[tuple[str, list[FidelidadRoute]]]:
    groups: list[tuple[str, list[FidelidadRoute]]] = []
    for route in FIDELIDAD_ROUTES if routes is None else routes:
        if not groups or groups[-1][0] != route.group:
            groups.append((route.group, []))
        groups[-1][1].append(route)
    return groups
