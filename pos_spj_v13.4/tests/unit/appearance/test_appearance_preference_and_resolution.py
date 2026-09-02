"""SET-22 — "Light/dark"/"Density": AppearancePreference entity +
appearance_resolution_policy.resolve_appearance. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.appearance.entities.appearance_preference import AppearancePreference
from backend.domain.appearance.enums import AppearanceScopeType, DensityLevel
from backend.domain.appearance.exceptions import AppearanceInvalidValueError
from backend.domain.appearance.policies.appearance_resolution_policy import resolve_appearance
from backend.shared.ids import is_uuidv7, new_uuid


def _preference(**overrides) -> AppearancePreference:
    kwargs = dict(
        scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=new_uuid(),
        density_level=DensityLevel.NORMAL,
    )
    kwargs.update(overrides)
    return AppearancePreference.create(**kwargs)


class TestAppearancePreferenceCreate:
    def test_mints_uuidv7_and_defaults_density(self):
        preference = AppearancePreference.create(
            scope_type=AppearanceScopeType.GLOBAL, scope_id=None, theme_id=new_uuid(),
        )
        assert is_uuidv7(preference.id)
        assert preference.density_level is DensityLevel.NORMAL
        assert preference.active is True

    def test_global_scope_rejects_scope_id(self):
        with pytest.raises(AppearanceInvalidValueError):
            _preference(scope_type=AppearanceScopeType.GLOBAL, scope_id=new_uuid())

    @pytest.mark.parametrize("scope_type", [AppearanceScopeType.BRANCH, AppearanceScopeType.USER])
    def test_non_global_scope_requires_scope_id(self, scope_type):
        with pytest.raises(AppearanceInvalidValueError):
            _preference(scope_type=scope_type, scope_id=None)

    def test_activate_deactivate(self):
        preference = _preference()
        preference.deactivate()
        assert preference.active is False
        preference.activate()
        assert preference.active is True

    def test_change_theme(self):
        preference = _preference()
        new_theme_id = new_uuid()
        preference.change_theme(new_theme_id)
        assert preference.theme_id == new_theme_id

    def test_change_density(self):
        preference = _preference()
        preference.change_density(DensityLevel.COMPACT)
        assert preference.density_level is DensityLevel.COMPACT


class TestAppearancePreferenceMatches:
    def test_matches_same_scope_when_active(self):
        branch_id = new_uuid()
        preference = _preference(scope_type=AppearanceScopeType.BRANCH, scope_id=branch_id)
        assert preference.matches(AppearanceScopeType.BRANCH, branch_id) is True

    def test_inactive_preference_never_matches(self):
        preference = _preference()
        preference.deactivate()
        assert preference.matches(AppearanceScopeType.GLOBAL, None) is False


class TestResolveAppearance:
    def test_falls_back_to_defaults_with_no_preferences(self):
        default_theme_id = new_uuid()
        theme_id, density = resolve_appearance([], default_theme_id=default_theme_id)
        assert theme_id == default_theme_id
        assert density is DensityLevel.NORMAL

    def test_global_preference_applies_to_any_context(self):
        global_theme_id = new_uuid()
        global_pref = _preference(theme_id=global_theme_id, density_level=DensityLevel.COMFORTABLE)
        theme_id, density = resolve_appearance(
            [global_pref], branch_id=new_uuid(), default_theme_id=new_uuid(),
        )
        assert theme_id == global_theme_id
        assert density is DensityLevel.COMFORTABLE

    def test_branch_preference_beats_global_preference(self):
        branch_id = new_uuid()
        global_theme_id, branch_theme_id = new_uuid(), new_uuid()
        global_pref = _preference(theme_id=global_theme_id)
        branch_pref = _preference(
            scope_type=AppearanceScopeType.BRANCH, scope_id=branch_id, theme_id=branch_theme_id,
            density_level=DensityLevel.COMPACT,
        )
        theme_id, density = resolve_appearance(
            [global_pref, branch_pref], branch_id=branch_id, default_theme_id=new_uuid(),
        )
        assert theme_id == branch_theme_id
        assert density is DensityLevel.COMPACT
        # A different branch still gets the global preference.
        other_theme_id, _ = resolve_appearance(
            [global_pref, branch_pref], branch_id=new_uuid(), default_theme_id=new_uuid(),
        )
        assert other_theme_id == global_theme_id

    def test_user_preference_beats_branch_and_global_preferences(self):
        branch_id, user_id = new_uuid(), new_uuid()
        global_pref = _preference(theme_id=new_uuid())
        branch_pref = _preference(
            scope_type=AppearanceScopeType.BRANCH, scope_id=branch_id, theme_id=new_uuid(),
        )
        user_theme_id = new_uuid()
        user_pref = _preference(
            scope_type=AppearanceScopeType.USER, scope_id=user_id, theme_id=user_theme_id,
            density_level=DensityLevel.COMFORTABLE,
        )
        theme_id, density = resolve_appearance(
            [global_pref, branch_pref, user_pref], branch_id=branch_id, user_id=user_id,
            default_theme_id=new_uuid(),
        )
        assert theme_id == user_theme_id
        assert density is DensityLevel.COMFORTABLE
