"""SET-22 — "Themes"/"Tokens": Theme + DesignToken entities,
theme_default_policy, token_resolution_policy. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.appearance.entities.design_token import DesignToken
from backend.domain.appearance.entities.theme import Theme
from backend.domain.appearance.enums import ThemeMode, TokenCategory
from backend.domain.appearance.exceptions import AppearanceInvalidValueError, DuplicateDefaultThemeError
from backend.domain.appearance.policies.theme_default_policy import assert_can_set_default
from backend.domain.appearance.policies.token_resolution_policy import resolve_tokens_for_theme
from backend.shared.ids import is_uuidv7, new_uuid


def _theme(**overrides) -> Theme:
    kwargs = dict(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
    kwargs.update(overrides)
    return Theme.create(**kwargs)


class TestThemeCreate:
    def test_mints_uuidv7_and_defaults(self):
        theme = _theme()
        assert is_uuidv7(theme.id)
        assert theme.active is True
        assert theme.is_default is False

    def test_requires_code(self):
        with pytest.raises(AppearanceInvalidValueError):
            _theme(code="   ")

    def test_requires_name(self):
        with pytest.raises(AppearanceInvalidValueError):
            _theme(name="   ")

    def test_activate_deactivate(self):
        theme = _theme()
        theme.deactivate()
        assert theme.active is False
        theme.activate()
        assert theme.active is True

    def test_mark_unmark_default(self):
        theme = _theme()
        theme.mark_default()
        assert theme.is_default is True
        theme.unmark_default()
        assert theme.is_default is False


class TestThemeUpdateDetails:
    def test_updates_name_and_bumps_updated_at(self):
        theme = _theme()
        original_updated_at = theme.updated_at
        theme.update_details(name="Oscuro medianoche")
        assert theme.name == "Oscuro medianoche"
        assert theme.updated_at >= original_updated_at

    def test_rejects_blank_name(self):
        theme = _theme()
        with pytest.raises(AppearanceInvalidValueError):
            theme.update_details(name="   ")

    def test_does_not_touch_code_or_mode(self):
        theme = _theme()
        original_code, original_mode = theme.code, theme.mode
        theme.update_details(name="Otro nombre")
        assert theme.code == original_code
        assert theme.mode == original_mode


class TestThemeDefaultPolicy:
    def test_allows_first_default(self):
        candidate = _theme(is_default=True)
        assert_can_set_default([], candidate)  # does not raise

    def test_allows_setting_default_on_the_same_theme_again(self):
        theme = _theme(is_default=True)
        assert_can_set_default([theme], theme)  # does not raise

    def test_rejects_a_second_active_default(self):
        existing = _theme(code="claro", name="Claro", mode=ThemeMode.LIGHT, is_default=True)
        candidate = _theme(code="oscuro", name="Oscuro", mode=ThemeMode.DARK, is_default=True)
        with pytest.raises(DuplicateDefaultThemeError):
            assert_can_set_default([existing], candidate)

    def test_allows_default_when_the_existing_default_is_inactive(self):
        existing = _theme(code="claro", name="Claro", mode=ThemeMode.LIGHT, is_default=True)
        existing.deactivate()
        candidate = _theme(code="oscuro", name="Oscuro", mode=ThemeMode.DARK, is_default=True)
        assert_can_set_default([existing], candidate)  # does not raise


def _token(**overrides) -> DesignToken:
    kwargs = dict(theme_id=None, token_key="spacing.md", category=TokenCategory.SPACING, token_value="16px")
    kwargs.update(overrides)
    return DesignToken.create(**kwargs)


class TestDesignTokenCreate:
    def test_mints_uuidv7_global_token(self):
        token = _token()
        assert is_uuidv7(token.id)
        assert token.theme_id is None

    def test_theme_scoped_token_validates_theme_id_as_uuidv7(self):
        theme_id = new_uuid()
        token = _token(theme_id=theme_id, token_key="color.background", category=TokenCategory.COLOR)
        assert token.theme_id == theme_id

    def test_requires_token_key(self):
        with pytest.raises(AppearanceInvalidValueError):
            _token(token_key="   ")

    def test_requires_token_value(self):
        with pytest.raises(AppearanceInvalidValueError):
            _token(token_value="   ")

    def test_update_value(self):
        token = _token()
        token.update_value("24px")
        assert token.token_value == "24px"

    def test_update_value_rejects_blank(self):
        token = _token()
        with pytest.raises(AppearanceInvalidValueError):
            token.update_value("   ")


class TestTokenResolutionPolicy:
    def test_global_only_tokens_resolve_as_is(self):
        tokens = [_token(token_key="spacing.md", token_value="16px")]
        resolved = resolve_tokens_for_theme(tokens, new_uuid())
        assert resolved == {"spacing.md": "16px"}

    def test_theme_scoped_token_overrides_global_token_with_same_key(self):
        theme_id = new_uuid()
        global_token = _token(token_key="color.background", token_value="#FFFFFF")
        theme_token = _token(
            theme_id=theme_id, token_key="color.background", category=TokenCategory.COLOR,
            token_value="#000000",
        )
        resolved = resolve_tokens_for_theme([global_token, theme_token], theme_id)
        assert resolved["color.background"] == "#000000"

    def test_tokens_scoped_to_a_different_theme_are_ignored(self):
        other_theme_id = new_uuid()
        other_theme_token = _token(
            theme_id=other_theme_id, token_key="color.background", category=TokenCategory.COLOR,
            token_value="#111111",
        )
        resolved = resolve_tokens_for_theme([other_theme_token], new_uuid())
        assert "color.background" not in resolved

    def test_global_token_still_applies_when_theme_has_no_override(self):
        theme_id = new_uuid()
        global_token = _token(token_key="spacing.md", token_value="16px")
        theme_token = _token(
            theme_id=theme_id, token_key="color.background", category=TokenCategory.COLOR,
            token_value="#000000",
        )
        resolved = resolve_tokens_for_theme([global_token, theme_token], theme_id)
        assert resolved == {"spacing.md": "16px", "color.background": "#000000"}
