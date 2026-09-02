"""Use cases for the "Apariencia" section's origination side — closes
the gap `set_default_theme_use_case.py` alone leaves open: nothing
previously called `Theme.create()`/`DesignToken.create()`/
`DensityProfile.create()`/`AppearancePreference.create()` outside of
tests, so `SetDefaultThemeUseCase` could never have a real `Theme` to
mark default. Same thin-orchestration shape as
`notification_management_use_cases.py`/
`feature_flag_management_use_cases.py`.

Occupancy checks (never let a raw `IntegrityError` reach the UI) mirror
the real unique constraints in `backend/infrastructure/db/schema/
appearance_schema.py`: `themes.code`, `density_profiles.level`,
`ux_design_tokens_scope` on `(theme_id, token_key)`, and
`ux_appearance_preferences_scope_active` on `(scope_type, scope_id)`
WHERE active=1 — the last one checked on both CREATE and the ACTIVATE
status action, same discipline `CreateNotificationRouteUseCase`/
`ChangeNotificationRouteStatusUseCase` (SET-20) already established.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from backend.domain.appearance.entities.appearance_preference import AppearancePreference
from backend.domain.appearance.entities.density_profile import DensityProfile
from backend.domain.appearance.entities.design_token import DesignToken
from backend.domain.appearance.entities.theme import Theme
from backend.domain.appearance.enums import AppearanceScopeType, DensityLevel, ThemeMode, TokenCategory
from backend.domain.appearance.exceptions import (
    AppearancePreferenceNotFoundError,
    AppearancePreferenceScopeOccupiedError,
    DensityProfileLevelOccupiedError,
    DensityProfileNotFoundError,
    DesignTokenNotFoundError,
    DesignTokenScopeOccupiedError,
    ThemeCodeOccupiedError,
    ThemeNotFoundError,
)
from backend.infrastructure.db.repositories.appearance.appearance_preference_repository import (
    SqliteAppearancePreferenceRepository,
)
from backend.infrastructure.db.repositories.appearance.density_profile_repository import (
    SqliteDensityProfileRepository,
)
from backend.infrastructure.db.repositories.appearance.design_token_repository import (
    SqliteDesignTokenRepository,
)
from backend.infrastructure.db.repositories.appearance.theme_repository import SqliteThemeRepository


class ThemeStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class DensityProfileStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class AppearancePreferenceStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


# ── Theme ─────────────────────────────────────────────────────────────────────

class CreateThemeUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._themes = SqliteThemeRepository(connection)

    def execute(self, *, code: str, name: str, mode: ThemeMode | str) -> Theme:
        if self._themes.get_by_code(code) is not None:
            raise ThemeCodeOccupiedError(f"Ya existe un tema con código {code!r}")
        theme = Theme.create(code=code, name=name, mode=ThemeMode(mode))
        self._themes.save(theme)
        self._conn.commit()
        return theme


class UpdateThemeUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._themes = SqliteThemeRepository(connection)

    def execute(self, *, theme_id: str, name: str) -> Theme:
        theme = self._themes.get(theme_id)
        if theme is None:
            raise ThemeNotFoundError(f"Tema {theme_id} no encontrado")
        theme.update_details(name=name)
        self._themes.save(theme)
        self._conn.commit()
        return theme


class ChangeThemeStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._themes = SqliteThemeRepository(connection)

    def execute(self, *, theme_id: str, action: ThemeStatusAction) -> Theme:
        theme = self._themes.get(theme_id)
        if theme is None:
            raise ThemeNotFoundError(f"Tema {theme_id} no encontrado")

        if action is ThemeStatusAction.ACTIVATE:
            theme.activate()
        elif action is ThemeStatusAction.DEACTIVATE:
            theme.deactivate()

        self._themes.save(theme)
        self._conn.commit()
        return theme


# ── DesignToken ───────────────────────────────────────────────────────────────

class CreateDesignTokenUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._tokens = SqliteDesignTokenRepository(connection)

    def execute(
        self, *, theme_id: str | None, token_key: str, category: TokenCategory | str, token_value: str,
    ) -> DesignToken:
        scope_key = theme_id or None
        candidates = self._tokens.list_for_theme(theme_id or "")
        existing = [
            t for t in candidates if t.theme_id == scope_key and t.token_key.strip() == token_key.strip()
        ]
        if existing:
            scope_label = "Global" if scope_key is None else scope_key
            raise DesignTokenScopeOccupiedError(
                f"Ya existe un token {token_key!r} en el alcance {scope_label!r}"
            )
        token = DesignToken.create(
            theme_id=theme_id, token_key=token_key, category=TokenCategory(category), token_value=token_value,
        )
        self._tokens.save(token)
        self._conn.commit()
        return token


class UpdateDesignTokenUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._tokens = SqliteDesignTokenRepository(connection)

    def execute(self, *, token_id: str, token_value: str) -> DesignToken:
        token = self._tokens.get(token_id)
        if token is None:
            raise DesignTokenNotFoundError(f"Token {token_id} no encontrado")
        token.update_value(token_value)
        self._tokens.save(token)
        self._conn.commit()
        return token


# ── DensityProfile ────────────────────────────────────────────────────────────

class CreateDensityProfileUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._profiles = SqliteDensityProfileRepository(connection)

    def execute(
        self, *, level: DensityLevel | str, name: str, scale_factor: Decimal, control_height_px: int,
        touch_target_px: int, spacing_unit_px: int,
    ) -> DensityProfile:
        level_enum = DensityLevel(level)
        if self._profiles.get_by_level(level_enum) is not None:
            raise DensityProfileLevelOccupiedError(f"Ya existe un perfil de densidad para {level_enum.value!r}")
        profile = DensityProfile.create(
            level=level_enum, name=name, scale_factor=scale_factor, control_height_px=control_height_px,
            touch_target_px=touch_target_px, spacing_unit_px=spacing_unit_px,
        )
        self._profiles.save(profile)
        self._conn.commit()
        return profile


class UpdateDensityProfileUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._profiles = SqliteDensityProfileRepository(connection)

    def execute(
        self, *, profile_id: str, name: str, scale_factor: Decimal, control_height_px: int,
        touch_target_px: int, spacing_unit_px: int,
    ) -> DensityProfile:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise DensityProfileNotFoundError(f"Perfil de densidad {profile_id} no encontrado")
        profile.update_details(
            name=name, scale_factor=scale_factor, control_height_px=control_height_px,
            touch_target_px=touch_target_px, spacing_unit_px=spacing_unit_px,
        )
        self._profiles.save(profile)
        self._conn.commit()
        return profile


class ChangeDensityProfileStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._profiles = SqliteDensityProfileRepository(connection)

    def execute(self, *, profile_id: str, action: DensityProfileStatusAction) -> DensityProfile:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise DensityProfileNotFoundError(f"Perfil de densidad {profile_id} no encontrado")

        if action is DensityProfileStatusAction.ACTIVATE:
            profile.activate()
        elif action is DensityProfileStatusAction.DEACTIVATE:
            profile.deactivate()

        self._profiles.save(profile)
        self._conn.commit()
        return profile


# ── AppearancePreference ─────────────────────────────────────────────────────

def _active_scope_occupant(
    preferences: SqliteAppearancePreferenceRepository, scope_type, scope_id, *, exclude_id=None,
):
    for preference in preferences.list_active():
        if preference.id == exclude_id:
            continue
        if preference.scope_type is scope_type and preference.scope_id == scope_id:
            return preference
    return None


class CreateAppearancePreferenceUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._preferences = SqliteAppearancePreferenceRepository(connection)

    def execute(
        self, *, scope_type: AppearanceScopeType | str, scope_id: str | None, theme_id: str,
        density_level: DensityLevel | str = DensityLevel.NORMAL,
    ) -> AppearancePreference:
        scope_type_enum = AppearanceScopeType(scope_type)
        if _active_scope_occupant(self._preferences, scope_type_enum, scope_id) is not None:
            raise AppearancePreferenceScopeOccupiedError(
                f"Ya existe una preferencia activa para el alcance {scope_type_enum.value!r}/{scope_id!r}"
            )
        preference = AppearancePreference.create(
            scope_type=scope_type_enum, scope_id=scope_id, theme_id=theme_id,
            density_level=DensityLevel(density_level),
        )
        self._preferences.save(preference)
        self._conn.commit()
        return preference


class ChangeAppearancePreferenceStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._preferences = SqliteAppearancePreferenceRepository(connection)

    def execute(self, *, preference_id: str, action: AppearancePreferenceStatusAction) -> AppearancePreference:
        preference = self._preferences.get(preference_id)
        if preference is None:
            raise AppearancePreferenceNotFoundError(f"Preferencia {preference_id} no encontrada")

        if action is AppearancePreferenceStatusAction.ACTIVATE:
            occupant = _active_scope_occupant(
                self._preferences, preference.scope_type, preference.scope_id, exclude_id=preference.id,
            )
            if occupant is not None:
                raise AppearancePreferenceScopeOccupiedError(
                    f"Ya existe una preferencia activa para el alcance "
                    f"{preference.scope_type.value!r}/{preference.scope_id!r}; desactívala primero"
                )
            preference.activate()
        elif action is AppearancePreferenceStatusAction.DEACTIVATE:
            preference.deactivate()

        self._preferences.save(preference)
        self._conn.commit()
        return preference
