"""Navigation model for the Tarjetas Fidelidad desktop workspace (LOY-25).

Mirrors ``frontend/desktop/modules/fidelidad/fidelidad_routes.py``'s shape.
Every route the LOY-16..23 backend phases built a bounded-context area for
is declared here, even though only a few have a real page today.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from frontend.desktop.modules.tarjetas_fidelidad.view_models import (
    TarjetasFidelidadCapabilities,
)


@dataclass(frozen=True)
class TarjetasFidelidadRoute:
    route_id: str
    label: str
    group: str
    tooltip: str
    required_permission: str
    capability: str


TARJETAS_FIDELIDAD_ROUTES: tuple[TarjetasFidelidadRoute, ...] = (
    TarjetasFidelidadRoute(
        route_id="tarjetas.overview", label="Resumen", group="Resumen",
        tooltip="Estado general de tarjetas de fidelidad.",
        required_permission=LoyaltyCardsPermissions.VIEW, capability="module_view"),

    TarjetasFidelidadRoute(
        route_id="tarjetas.cards", label="Tarjetas", group="Tarjetas",
        tooltip="Emisión, activación, bloqueo y reposición de tarjetas.",
        required_permission=LoyaltyCardsPermissions.CARD_VIEW, capability="cards"),
    TarjetasFidelidadRoute(
        route_id="tarjetas.digital", label="Tarjeta digital", group="Tarjetas",
        tooltip="Proyección de tarjeta digital para wallet/app.",
        required_permission=LoyaltyCardsPermissions.CARD_VIEW, capability="cards"),

    TarjetasFidelidadRoute(
        route_id="tarjetas.templates", label="Plantillas", group="Diseño",
        tooltip="Plantillas y versiones de diseño.",
        required_permission=LoyaltyCardsPermissions.TEMPLATE_VIEW, capability="templates"),
    TarjetasFidelidadRoute(
        route_id="tarjetas.designer", label="Diseñador", group="Diseño",
        tooltip="Estudio de diseño de tarjetas.",
        required_permission=LoyaltyCardsPermissions.DESIGNER_ACCESS, capability="templates"),

    TarjetasFidelidadRoute(
        route_id="tarjetas.sheets", label="Pliegos", group="Producción",
        tooltip="Perfiles de pliego e imposición.",
        required_permission=LoyaltyCardsPermissions.FORMAT_MANAGE, capability="sheets"),
    TarjetasFidelidadRoute(
        route_id="tarjetas.batches", label="Lotes", group="Producción",
        tooltip="Lotes de tarjetas físicas.",
        required_permission=LoyaltyCardsPermissions.BATCH_CREATE, capability="batches"),
    TarjetasFidelidadRoute(
        route_id="tarjetas.printing", label="Impresión", group="Producción",
        tooltip="Impresión y reimpresión de lotes.",
        required_permission=LoyaltyCardsPermissions.BATCH_PRINT, capability="batches"),
)


def visible_routes(
    capabilities: TarjetasFidelidadCapabilities,
) -> tuple[TarjetasFidelidadRoute, ...]:
    if not capabilities.module_view:
        return ()
    return tuple(
        route for route in TARJETAS_FIDELIDAD_ROUTES
        if bool(getattr(capabilities, route.capability, False)))


def grouped_routes(
    routes: tuple[TarjetasFidelidadRoute, ...] | list[TarjetasFidelidadRoute] | None = None,
) -> list[tuple[str, list[TarjetasFidelidadRoute]]]:
    groups: list[tuple[str, list[TarjetasFidelidadRoute]]] = []
    for route in TARJETAS_FIDELIDAD_ROUTES if routes is None else routes:
        if not groups or groups[-1][0] != route.group:
            groups.append((route.group, []))
        groups[-1][1].append(route)
    return groups
