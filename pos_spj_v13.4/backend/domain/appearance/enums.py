"""Canonical enums for the Appearance bounded context — SET-22.

Legacy inventory: three parallel, inconsistent theme systems coexist
today — `ui/themes/theme_engine.py` (raw SQL against the generic
`configuraciones(clave, valor)` table, key `'tema'`, only "Claro"/"Oscuro"
strings), `core/services/theme_service.py` (`ThemeService`, reads/writes
keys `ui_theme`/`ui_density`/`ui_font_size`/`ui_icon_size` from the same
generic table, `density` is an unvalidated free string defaulting to
`'Normal'`), and `frontend/desktop/themes/` (a newer "FASE DS-2" design
system — `theme_manager.py` with `VALID_THEMES=("light","dark")` and a
real `tokens.py` module, but no DB persistence and no density concept at
all). `modulos/config_interfaz.py` (the "Apariencia" settings screen) is
already broken today — it references `theme_service.palettes`/`.densities`
attributes that do not exist on `ThemeService`.

This bounded context generalizes all three into one typed, persisted
model: `ThemeMode` mirrors the legacy Claro/Oscuro (light/dark) split,
`DensityLevel` gives the free-string `density` preference a real enum for
the first time, and `AppearanceScopeType` generalizes the legacy
single-global preference into per-branch/per-user overrides (no legacy
precedent — `configuraciones` has no scoping at all).
"""

from __future__ import annotations

from enum import Enum


class ThemeMode(str, Enum):
    """Generalizes the legacy "Claro"/"Oscuro" (and `SPJ_LIGHT`/`SPJ_DARK`
    aliases) two-theme split used by `ui/themes/theme_engine.py`."""

    LIGHT = "LIGHT"
    DARK = "DARK"


class DensityLevel(str, Enum):
    """The legacy `density` preference (`core/services/theme_service.py`)
    is a free, unvalidated string defaulting to `'Normal'` with no defined
    set of options. This is the first typed enumeration of it."""

    COMPACT = "COMPACT"
    NORMAL = "NORMAL"
    COMFORTABLE = "COMFORTABLE"


class TokenCategory(str, Enum):
    """Mirrors the module names already used by the newer
    `frontend/desktop/themes/tokens.py` design-tokens module (Spacing,
    Typography, Radii, Borders, Elevation, ControlHeights, IconSizes) —
    reused here as an explicit domain enum instead of a set of Python
    classes with no persisted, admin-editable representation."""

    COLOR = "COLOR"
    SPACING = "SPACING"
    TYPOGRAPHY = "TYPOGRAPHY"
    RADIUS = "RADIUS"
    BORDER = "BORDER"
    ELEVATION = "ELEVATION"
    ICON_SIZE = "ICON_SIZE"
    CONTROL_HEIGHT = "CONTROL_HEIGHT"


class AppearanceScopeType(str, Enum):
    """How specific an `AppearancePreference` targets. No legacy
    precedent — `configuraciones` stores exactly one global theme/density
    pair with no scoping at all. Mirrors
    `backend.domain.feature_flags.enums.FeatureFlagScopeType` (bounded-
    context independence — reimplemented, not imported)."""

    GLOBAL = "GLOBAL"
    BRANCH = "BRANCH"
    USER = "USER"


# Most specific first — the order `policies/appearance_resolution_policy.py`
# uses to pick a preference when more than one could apply.
SCOPE_SPECIFICITY_ORDER: tuple[AppearanceScopeType, ...] = (
    AppearanceScopeType.USER, AppearanceScopeType.BRANCH, AppearanceScopeType.GLOBAL,
)
