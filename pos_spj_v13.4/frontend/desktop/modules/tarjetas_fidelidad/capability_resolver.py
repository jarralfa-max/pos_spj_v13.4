"""Single permission-to-capability map for the Tarjetas Fidelidad UI
(LOY-25). Mirrors ``frontend/desktop/modules/fidelidad/capability_resolver.py``,
reusing ``LoyaltyCardsPermissions`` (LOY-1) — no new permission codes
needed."""

from __future__ import annotations

from collections.abc import Callable

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from frontend.desktop.modules.tarjetas_fidelidad.view_models import (
    TarjetasFidelidadCapabilities,
)


def resolve_tarjetas_fidelidad_capabilities(
    can: Callable[[str], bool],
) -> TarjetasFidelidadCapabilities:
    return TarjetasFidelidadCapabilities(
        module_view=can(LoyaltyCardsPermissions.VIEW),
        cards=can(LoyaltyCardsPermissions.CARD_VIEW),
        templates=can(LoyaltyCardsPermissions.TEMPLATE_VIEW),
        batches=can(LoyaltyCardsPermissions.BATCH_CREATE) or can(LoyaltyCardsPermissions.CARD_VIEW),
        sheets=can(LoyaltyCardsPermissions.FORMAT_MANAGE) or can(LoyaltyCardsPermissions.CARD_VIEW),
    )
