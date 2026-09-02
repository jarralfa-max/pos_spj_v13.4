"""SET-22 — "Density": DensityProfile entity. Pure domain — no DB."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.appearance.entities.density_profile import DensityProfile
from backend.domain.appearance.enums import DensityLevel
from backend.domain.appearance.exceptions import AppearanceInvalidValueError
from backend.shared.ids import is_uuidv7


def _profile(**overrides) -> DensityProfile:
    kwargs = dict(
        level=DensityLevel.NORMAL, name="Normal", scale_factor=Decimal("1.0"), control_height_px=36,
        touch_target_px=44, spacing_unit_px=8,
    )
    kwargs.update(overrides)
    return DensityProfile.create(**kwargs)


class TestDensityProfileCreate:
    def test_mints_uuidv7_and_defaults(self):
        profile = _profile()
        assert is_uuidv7(profile.id)
        assert profile.active is True
        assert profile.scale_factor == Decimal("1.0")

    def test_requires_name(self):
        with pytest.raises(AppearanceInvalidValueError):
            _profile(name="   ")

    def test_rejects_non_decimal_scale_factor(self):
        with pytest.raises(AppearanceInvalidValueError):
            _profile(scale_factor=1.0)  # float, not Decimal — never float for business values

    def test_rejects_zero_or_negative_scale_factor(self):
        with pytest.raises(AppearanceInvalidValueError):
            _profile(scale_factor=Decimal("0"))
        with pytest.raises(AppearanceInvalidValueError):
            _profile(scale_factor=Decimal("-0.5"))

    @pytest.mark.parametrize("field_name", ["control_height_px", "touch_target_px", "spacing_unit_px"])
    def test_rejects_zero_or_negative_pixel_metrics(self, field_name):
        with pytest.raises(AppearanceInvalidValueError):
            _profile(**{field_name: 0})
        with pytest.raises(AppearanceInvalidValueError):
            _profile(**{field_name: -10})

    @pytest.mark.parametrize("field_name", ["control_height_px", "touch_target_px", "spacing_unit_px"])
    def test_rejects_bool_for_pixel_metrics(self, field_name):
        with pytest.raises(AppearanceInvalidValueError):
            _profile(**{field_name: True})

    def test_compact_and_comfortable_profiles_are_independent_levels(self):
        compact = _profile(level=DensityLevel.COMPACT, name="Compacto", scale_factor=Decimal("0.85"))
        comfortable = _profile(
            level=DensityLevel.COMFORTABLE, name="Confortable", scale_factor=Decimal("1.15"),
        )
        assert compact.level is DensityLevel.COMPACT
        assert comfortable.level is DensityLevel.COMFORTABLE
        assert compact.scale_factor < comfortable.scale_factor

    def test_activate_deactivate(self):
        profile = _profile()
        profile.deactivate()
        assert profile.active is False
        profile.activate()
        assert profile.active is True


class TestDensityProfileUpdateDetails:
    def test_updates_fields_and_bumps_updated_at(self):
        profile = _profile()
        original_updated_at = profile.updated_at
        profile.update_details(
            name="Normal ajustado", scale_factor=Decimal("1.1"), control_height_px=40,
            touch_target_px=48, spacing_unit_px=10,
        )
        assert profile.name == "Normal ajustado"
        assert profile.scale_factor == Decimal("1.1")
        assert profile.control_height_px == 40
        assert profile.touch_target_px == 48
        assert profile.spacing_unit_px == 10
        assert profile.updated_at >= original_updated_at

    def test_rejects_invalid_scale_factor(self):
        profile = _profile()
        with pytest.raises(AppearanceInvalidValueError):
            profile.update_details(
                name="X", scale_factor=Decimal("0"), control_height_px=40, touch_target_px=48,
                spacing_unit_px=10,
            )

    def test_does_not_touch_level(self):
        profile = _profile()
        original_level = profile.level
        profile.update_details(
            name="Y", scale_factor=Decimal("1.0"), control_height_px=36, touch_target_px=44,
            spacing_unit_px=8,
        )
        assert profile.level == original_level
