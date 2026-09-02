"""SET-22 repegado — CreateThemeUseCase/UpdateThemeUseCase/
ChangeThemeStatusUseCase, CreateDesignTokenUseCase/UpdateDesignTokenUseCase,
CreateDensityProfileUseCase/UpdateDensityProfileUseCase/
ChangeDensityProfileStatusUseCase, CreateAppearancePreferenceUseCase/
ChangeAppearancePreferenceStatusUseCase against a real (in-memory) SQLite
born-clean schema (migration 222). These close the origination gap:
before this round nothing called `Theme.create()`/`DesignToken.create()`/
`DensityProfile.create()`/`AppearancePreference.create()` outside of
tests, so `SetDefaultThemeUseCase` could never have a real `Theme` to
mark default.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

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
from backend.application.use_cases.configuracion.appearance_management_use_cases import (
    AppearancePreferenceStatusAction,
    ChangeAppearancePreferenceStatusUseCase,
    ChangeDensityProfileStatusUseCase,
    ChangeThemeStatusUseCase,
    CreateAppearancePreferenceUseCase,
    CreateDensityProfileUseCase,
    CreateDesignTokenUseCase,
    CreateThemeUseCase,
    DensityProfileStatusAction,
    ThemeStatusAction,
    UpdateDensityProfileUseCase,
    UpdateDesignTokenUseCase,
    UpdateThemeUseCase,
)
from backend.infrastructure.db.repositories.appearance.theme_repository import SqliteThemeRepository
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _create_theme(conn, **overrides):
    kwargs = dict(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
    kwargs.update(overrides)
    return CreateThemeUseCase(conn).execute(**kwargs)


class TestCreateThemeUseCase:
    def test_creates_and_persists(self, conn):
        theme = _create_theme(conn)
        assert SqliteThemeRepository(conn).get(theme.id) is not None

    def test_rejects_duplicate_code(self, conn):
        _create_theme(conn, code="dup")
        with pytest.raises(ThemeCodeOccupiedError):
            _create_theme(conn, code="dup", name="Otro")


class TestUpdateThemeUseCase:
    def test_updates_name(self, conn):
        theme = _create_theme(conn)
        updated = UpdateThemeUseCase(conn).execute(theme_id=theme.id, name="Oscuro medianoche")
        assert updated.name == "Oscuro medianoche"

    def test_raises_when_missing(self, conn):
        with pytest.raises(ThemeNotFoundError):
            UpdateThemeUseCase(conn).execute(theme_id=new_uuid(), name="X")


class TestChangeThemeStatusUseCase:
    def test_deactivate_then_activate(self, conn):
        theme = _create_theme(conn)
        uc = ChangeThemeStatusUseCase(conn)
        deactivated = uc.execute(theme_id=theme.id, action=ThemeStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = uc.execute(theme_id=theme.id, action=ThemeStatusAction.ACTIVATE)
        assert activated.active is True


class TestCreateDesignTokenUseCase:
    def test_creates_global_token(self, conn):
        token = CreateDesignTokenUseCase(conn).execute(
            theme_id=None, token_key="spacing.md", category=TokenCategory.SPACING, token_value="16px")
        assert token.theme_id is None

    def test_creates_theme_scoped_token(self, conn):
        theme = _create_theme(conn)
        token = CreateDesignTokenUseCase(conn).execute(
            theme_id=theme.id, token_key="color.background", category=TokenCategory.COLOR,
            token_value="#000000")
        assert token.theme_id == theme.id

    def test_rejects_duplicate_key_in_same_scope(self, conn):
        uc = CreateDesignTokenUseCase(conn)
        uc.execute(theme_id=None, token_key="spacing.md", category=TokenCategory.SPACING, token_value="16px")
        with pytest.raises(DesignTokenScopeOccupiedError):
            uc.execute(theme_id=None, token_key="spacing.md", category=TokenCategory.SPACING, token_value="8px")

    def test_allows_same_key_in_different_scopes(self, conn):
        theme = _create_theme(conn)
        uc = CreateDesignTokenUseCase(conn)
        global_token = uc.execute(
            theme_id=None, token_key="color.accent", category=TokenCategory.COLOR, token_value="#FFF")
        theme_token = uc.execute(
            theme_id=theme.id, token_key="color.accent", category=TokenCategory.COLOR, token_value="#000")
        assert global_token.id != theme_token.id


class TestUpdateDesignTokenUseCase:
    def test_updates_value(self, conn):
        token = CreateDesignTokenUseCase(conn).execute(
            theme_id=None, token_key="spacing.md", category=TokenCategory.SPACING, token_value="16px")
        updated = UpdateDesignTokenUseCase(conn).execute(token_id=token.id, token_value="24px")
        assert updated.token_value == "24px"

    def test_raises_when_missing(self, conn):
        with pytest.raises(DesignTokenNotFoundError):
            UpdateDesignTokenUseCase(conn).execute(token_id=new_uuid(), token_value="24px")


def _create_density_profile(conn, **overrides):
    kwargs = dict(
        level=DensityLevel.NORMAL, name="Normal", scale_factor=Decimal("1.0"), control_height_px=36,
        touch_target_px=44, spacing_unit_px=8,
    )
    kwargs.update(overrides)
    return CreateDensityProfileUseCase(conn).execute(**kwargs)


class TestCreateDensityProfileUseCase:
    def test_creates_and_persists(self, conn):
        profile = _create_density_profile(conn)
        assert profile.level is DensityLevel.NORMAL

    def test_rejects_duplicate_level(self, conn):
        _create_density_profile(conn)
        with pytest.raises(DensityProfileLevelOccupiedError):
            _create_density_profile(conn, name="Normal 2")


class TestUpdateDensityProfileUseCase:
    def test_updates_fields(self, conn):
        profile = _create_density_profile(conn)
        updated = UpdateDensityProfileUseCase(conn).execute(
            profile_id=profile.id, name="Normal ajustado", scale_factor=Decimal("1.1"),
            control_height_px=40, touch_target_px=48, spacing_unit_px=10,
        )
        assert updated.name == "Normal ajustado"
        assert updated.scale_factor == Decimal("1.1")

    def test_raises_when_missing(self, conn):
        with pytest.raises(DensityProfileNotFoundError):
            UpdateDensityProfileUseCase(conn).execute(
                profile_id=new_uuid(), name="X", scale_factor=Decimal("1.0"), control_height_px=36,
                touch_target_px=44, spacing_unit_px=8,
            )


class TestChangeDensityProfileStatusUseCase:
    def test_deactivate_then_activate(self, conn):
        profile = _create_density_profile(conn)
        uc = ChangeDensityProfileStatusUseCase(conn)
        deactivated = uc.execute(profile_id=profile.id, action=DensityProfileStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = uc.execute(profile_id=profile.id, action=DensityProfileStatusAction.ACTIVATE)
        assert activated.active is True


class TestCreateAppearancePreferenceUseCase:
    def test_creates_global_preference(self, conn):
        theme = _create_theme(conn)
        preference = CreateAppearancePreferenceUseCase(conn).execute(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
            density_level=DensityLevel.NORMAL,
        )
        assert preference.scope_type is AppearanceScopeType.GLOBAL

    def test_rejects_second_active_preference_in_same_scope(self, conn):
        theme = _create_theme(conn)
        uc = CreateAppearancePreferenceUseCase(conn)
        uc.execute(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
            density_level=DensityLevel.NORMAL,
        )
        with pytest.raises(AppearancePreferenceScopeOccupiedError):
            uc.execute(
                scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
                density_level=DensityLevel.COMPACT,
            )

    def test_allows_different_scopes(self, conn):
        theme = _create_theme(conn)
        uc = CreateAppearancePreferenceUseCase(conn)
        branch_id = new_uuid()
        global_pref = uc.execute(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
            density_level=DensityLevel.NORMAL,
        )
        branch_pref = uc.execute(
            scope_type=AppearanceScopeType.BRANCH, scope_id=branch_id, theme_id=theme.id,
            density_level=DensityLevel.COMPACT,
        )
        assert global_pref.id != branch_pref.id


class TestChangeAppearancePreferenceStatusUseCase:
    def test_deactivate_then_reactivate(self, conn):
        theme = _create_theme(conn)
        preference = CreateAppearancePreferenceUseCase(conn).execute(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
            density_level=DensityLevel.NORMAL,
        )
        uc = ChangeAppearancePreferenceStatusUseCase(conn)
        deactivated = uc.execute(
            preference_id=preference.id, action=AppearancePreferenceStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = uc.execute(
            preference_id=preference.id, action=AppearancePreferenceStatusAction.ACTIVATE)
        assert activated.active is True

    def test_activate_rejects_when_scope_already_occupied(self, conn):
        theme = _create_theme(conn)
        create_uc = CreateAppearancePreferenceUseCase(conn)
        first = create_uc.execute(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
            density_level=DensityLevel.NORMAL,
        )
        status_uc = ChangeAppearancePreferenceStatusUseCase(conn)
        status_uc.execute(preference_id=first.id, action=AppearancePreferenceStatusAction.DEACTIVATE)
        second = create_uc.execute(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
            density_level=DensityLevel.COMPACT,
        )
        with pytest.raises(AppearancePreferenceScopeOccupiedError):
            status_uc.execute(preference_id=first.id, action=AppearancePreferenceStatusAction.ACTIVATE)

    def test_raises_when_missing(self, conn):
        with pytest.raises(AppearancePreferenceNotFoundError):
            ChangeAppearancePreferenceStatusUseCase(conn).execute(
                preference_id=new_uuid(), action=AppearancePreferenceStatusAction.ACTIVATE)
