"""Domain exceptions for the Appearance bounded context — SET-22.
Mirrors backend/domain/feature_flags/exceptions.py's shape.
"""

from __future__ import annotations


class AppearanceDomainError(Exception):
    """Base for Appearance rule violations."""


class AppearanceInvalidValueError(AppearanceDomainError):
    """A field does not satisfy its validation rule."""


class ThemeNotFoundError(AppearanceDomainError):
    """Referenced a `Theme` id/code that does not exist."""


class DuplicateDefaultThemeError(AppearanceDomainError):
    """Only one `Theme` may be marked `is_default` at a time — mirrors
    the singleton constraint the schema layer also enforces via
    `ux_themes_single_default`, checked here too (defense in depth) so
    the violation surfaces as a domain error before it ever reaches the
    database."""


class DensityProfileNotFoundError(AppearanceDomainError):
    """Referenced a `DensityProfile` id/level that does not exist."""


class ThemeCodeOccupiedError(AppearanceDomainError):
    """`Theme.code` must be unique; another theme already uses it."""


class DesignTokenNotFoundError(AppearanceDomainError):
    """Referenced a `DesignToken` id that does not exist."""


class DesignTokenScopeOccupiedError(AppearanceDomainError):
    """`(theme_id, token_key)` must be unique; another token already
    occupies this scope (mirrors `ux_design_tokens_scope`)."""


class DensityProfileLevelOccupiedError(AppearanceDomainError):
    """`DensityProfile.level` must be unique; another profile already
    uses it."""


class AppearancePreferenceNotFoundError(AppearanceDomainError):
    """Referenced an `AppearancePreference` id that does not exist."""


class AppearancePreferenceScopeOccupiedError(AppearanceDomainError):
    """At most one ACTIVE `AppearancePreference` may exist per
    `(scope_type, scope_id)` (mirrors
    `ux_appearance_preferences_scope_active`)."""
