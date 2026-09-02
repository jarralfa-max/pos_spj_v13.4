"""View-models for the Tarjetas Fidelidad desktop workspace (LOY-25).

Same coarse-capability-per-nav-group shape as
``frontend/desktop/modules/fidelidad/view_models.py``, mapped to
``LoyaltyCardsPermissions`` (LOY-1) instead — Loyalty Cards has its own
``TARJETAS_FIDELIDAD`` permission surface, a separate bounded context from
Fidelidad even though both live under the same "Fidelización" umbrella in
the sidebar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TarjetasFidelidadCapabilities:
    module_view: bool = False
    cards: bool = False
    templates: bool = False
    batches: bool = False
    sheets: bool = False
