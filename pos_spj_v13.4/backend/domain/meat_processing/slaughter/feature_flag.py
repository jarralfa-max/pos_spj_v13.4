"""Slaughter feature gate (§37/§50, PROC-24).

Mirrors `backend.domain.inventory.slaughter.planning.SLAUGHTER_ENABLED` —
a plain module constant, not the formal `backend/domain/feature_flags/`
runtime system (which exists for admin-configurable, per-branch toggles on
*shipping* features). Slaughter has no real implementation yet to toggle at
runtime; this is a code-level guard that keeps it off until a real module
lands, consistent with the sibling stub in Inventory.
"""

from __future__ import annotations

from backend.domain.meat_processing.exceptions import MeatProcessingConfigurationError

#: The slaughter module is not implemented; this stays False until it lands.
SLAUGHTER_ENABLED = False


def ensure_slaughter_enabled() -> None:
    if not SLAUGHTER_ENABLED:
        raise MeatProcessingConfigurationError(
            "El módulo de sacrificio aún no está habilitado")
