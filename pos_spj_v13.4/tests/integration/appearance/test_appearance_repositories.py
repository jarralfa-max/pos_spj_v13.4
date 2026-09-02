"""SET-22 — SqliteThemeRepository + SqliteDesignTokenRepository +
SqliteDensityProfileRepository + SqliteAppearancePreferenceRepository
against a real (in-memory) SQLite born-clean schema (migration 222).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.appearance.entities.appearance_preference import AppearancePreference
from backend.domain.appearance.entities.density_profile import DensityProfile
from backend.domain.appearance.entities.design_token import DesignToken
from backend.domain.appearance.entities.theme import Theme
from backend.domain.appearance.enums import AppearanceScopeType, DensityLevel, ThemeMode, TokenCategory
from backend.domain.appearance.policies.appearance_resolution_policy import resolve_appearance
from backend.domain.appearance.policies.token_resolution_policy import resolve_tokens_for_theme
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
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def theme_repo(conn):
    return SqliteThemeRepository(conn)


@pytest.fixture
def token_repo(conn):
    return SqliteDesignTokenRepository(conn)


@pytest.fixture
def density_repo(conn):
    return SqliteDensityProfileRepository(conn)


@pytest.fixture
def preference_repo(conn):
    return SqliteAppearancePreferenceRepository(conn)


class TestThemeRepository:
    def test_save_get_roundtrip(self, conn, theme_repo):
        theme = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
        theme_repo.save(theme)
        conn.commit()

        fetched = theme_repo.get(theme.id)
        assert fetched.code == "oscuro"
        assert fetched.mode is ThemeMode.DARK

    def test_get_by_code(self, conn, theme_repo):
        theme = Theme.create(code="claro", name="Claro", mode=ThemeMode.LIGHT)
        theme_repo.save(theme)
        conn.commit()
        assert theme_repo.get_by_code("claro").id == theme.id

    def test_code_is_unique(self, conn, theme_repo):
        theme_repo.save(Theme.create(code="oscuro", name="A", mode=ThemeMode.DARK))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            theme_repo.save(Theme.create(code="oscuro", name="B", mode=ThemeMode.LIGHT))
            conn.commit()
        conn.rollback()

    def test_get_default(self, conn, theme_repo):
        theme = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK, is_default=True)
        theme_repo.save(theme)
        conn.commit()
        assert theme_repo.get_default().id == theme.id

    def test_only_one_default_theme_allowed_at_schema_level(self, conn, theme_repo):
        first = Theme.create(code="claro", name="Claro", mode=ThemeMode.LIGHT, is_default=True)
        second = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK, is_default=True)
        theme_repo.save(first)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            theme_repo.save(second)
            conn.commit()
        conn.rollback()

    def test_list_active_excludes_inactive(self, conn, theme_repo):
        active = Theme.create(code="claro", name="Claro", mode=ThemeMode.LIGHT)
        inactive = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
        inactive.deactivate()
        theme_repo.save(active)
        theme_repo.save(inactive)
        conn.commit()

        codes = {t.code for t in theme_repo.list_active()}
        assert codes == {"claro"}


class TestDesignTokenRepository:
    def _saved_theme(self, conn, theme_repo) -> Theme:
        theme = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
        theme_repo.save(theme)
        conn.commit()
        return theme

    def test_save_get_roundtrip(self, conn, theme_repo, token_repo):
        theme = self._saved_theme(conn, theme_repo)
        token = DesignToken.create(
            theme_id=theme.id, token_key="color.background", category=TokenCategory.COLOR,
            token_value="#000000",
        )
        token_repo.save(token)
        conn.commit()

        fetched = token_repo.get(token.id)
        assert fetched.token_value == "#000000"
        assert fetched.category is TokenCategory.COLOR

    def test_scope_uniqueness_blocks_duplicate_key_for_same_theme(self, conn, theme_repo, token_repo):
        theme = self._saved_theme(conn, theme_repo)
        first = DesignToken.create(
            theme_id=theme.id, token_key="color.background", category=TokenCategory.COLOR,
            token_value="#000000",
        )
        second = DesignToken.create(
            theme_id=theme.id, token_key="color.background", category=TokenCategory.COLOR,
            token_value="#111111",
        )
        token_repo.save(first)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            token_repo.save(second)
            conn.commit()
        conn.rollback()

    def test_composes_with_token_resolution_policy_end_to_end(self, conn, theme_repo, token_repo):
        theme = self._saved_theme(conn, theme_repo)
        global_token = DesignToken.create(
            theme_id=None, token_key="spacing.md", category=TokenCategory.SPACING, token_value="16px",
        )
        theme_token = DesignToken.create(
            theme_id=theme.id, token_key="color.background", category=TokenCategory.COLOR,
            token_value="#000000",
        )
        token_repo.save(global_token)
        token_repo.save(theme_token)
        conn.commit()

        resolved = resolve_tokens_for_theme(token_repo.list_for_theme(theme.id), theme.id)
        assert resolved == {"spacing.md": "16px", "color.background": "#000000"}


class TestDensityProfileRepository:
    def test_save_get_roundtrip_preserves_decimal_scale_factor(self, conn, density_repo):
        profile = DensityProfile.create(
            level=DensityLevel.COMPACT, name="Compacto", scale_factor=Decimal("0.85"),
            control_height_px=28, touch_target_px=36, spacing_unit_px=6,
        )
        density_repo.save(profile)
        conn.commit()

        fetched = density_repo.get(profile.id)
        assert fetched.scale_factor == Decimal("0.85")
        assert isinstance(fetched.scale_factor, Decimal)

    def test_get_by_level(self, conn, density_repo):
        profile = DensityProfile.create(
            level=DensityLevel.NORMAL, name="Normal", scale_factor=Decimal("1.0"), control_height_px=36,
            touch_target_px=44, spacing_unit_px=8,
        )
        density_repo.save(profile)
        conn.commit()
        assert density_repo.get_by_level(DensityLevel.NORMAL).id == profile.id

    def test_level_is_unique(self, conn, density_repo):
        density_repo.save(DensityProfile.create(
            level=DensityLevel.NORMAL, name="Normal", scale_factor=Decimal("1.0"), control_height_px=36,
            touch_target_px=44, spacing_unit_px=8,
        ))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            density_repo.save(DensityProfile.create(
                level=DensityLevel.NORMAL, name="Normal duplicado", scale_factor=Decimal("1.0"),
                control_height_px=36, touch_target_px=44, spacing_unit_px=8,
            ))
            conn.commit()
        conn.rollback()


class TestAppearancePreferenceRepository:
    def test_save_get_roundtrip(self, conn, theme_repo, preference_repo):
        theme = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
        theme_repo.save(theme)
        conn.commit()

        preference = AppearancePreference.create(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
            density_level=DensityLevel.COMFORTABLE,
        )
        preference_repo.save(preference)
        conn.commit()

        fetched = preference_repo.get(preference.id)
        assert fetched.theme_id == theme.id
        assert fetched.density_level is DensityLevel.COMFORTABLE

    def test_unique_index_blocks_two_active_preferences_for_same_scope(self, conn, theme_repo, preference_repo):
        theme = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
        theme_repo.save(theme)
        conn.commit()

        first = AppearancePreference.create(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
        )
        second = AppearancePreference.create(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=theme.id,
        )
        preference_repo.save(first)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            preference_repo.save(second)
            conn.commit()
        conn.rollback()

    def test_composes_with_resolution_policy_end_to_end(self, conn, theme_repo, preference_repo):
        global_theme = Theme.create(code="claro", name="Claro", mode=ThemeMode.LIGHT)
        branch_theme = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
        theme_repo.save(global_theme)
        theme_repo.save(branch_theme)
        conn.commit()

        branch_id = new_uuid()
        global_pref = AppearancePreference.create(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=global_theme.id,
        )
        branch_pref = AppearancePreference.create(
            scope_type=AppearanceScopeType.BRANCH, scope_id=branch_id, theme_id=branch_theme.id,
            density_level=DensityLevel.COMPACT,
        )
        preference_repo.save(global_pref)
        preference_repo.save(branch_pref)
        conn.commit()

        fetched_preferences = preference_repo.list_active()
        theme_id, density = resolve_appearance(
            fetched_preferences, branch_id=branch_id, default_theme_id=new_uuid(),
        )
        assert theme_id == branch_theme.id
        assert density is DensityLevel.COMPACT

        other_theme_id, _ = resolve_appearance(
            fetched_preferences, branch_id=new_uuid(), default_theme_id=new_uuid(),
        )
        assert other_theme_id == global_theme.id
