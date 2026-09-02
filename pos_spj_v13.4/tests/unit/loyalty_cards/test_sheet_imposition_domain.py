"""LOY-20 — LoyaltyCardSheetProfile / LoyaltyCardImpositionProfile /
ImpositionPolicy (master prompt §38-40)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty_cards.entities.loyalty_card_imposition_profile import (
    LoyaltyCardImpositionProfile,
)
from backend.domain.loyalty_cards.entities.loyalty_card_sheet_profile import (
    MM_PER_INCH,
    LoyaltyCardSheetProfile,
)
from backend.domain.loyalty_cards.exceptions import (
    CardDoesNotFitOnSheetError,
    InvalidImpositionProfileError,
    InvalidSheetProfileError,
)
from backend.domain.loyalty_cards.policies.imposition_policy import ImpositionPolicy


class TestLoyaltyCardSheetProfile:
    def test_requires_positive_dimensions(self):
        with pytest.raises(InvalidSheetProfileError):
            LoyaltyCardSheetProfile.create("S1", "Pliego", Decimal("0"), Decimal("100"))

    def test_rejects_float_dimensions(self):
        with pytest.raises(InvalidSheetProfileError):
            LoyaltyCardSheetProfile.create("S1", "Pliego", 100.5, 200)

    def test_margins_cannot_consume_whole_width(self):
        with pytest.raises(InvalidSheetProfileError):
            LoyaltyCardSheetProfile.create(
                "S1", "Pliego", Decimal("100"), Decimal("100"),
                margin_left_mm=Decimal("50"), margin_right_mm=Decimal("50"))

    def test_printable_dimensions(self):
        profile = LoyaltyCardSheetProfile.create(
            "S1", "Pliego", Decimal("300"), Decimal("450"),
            margin_top_mm=Decimal("10"), margin_bottom_mm=Decimal("10"),
            margin_left_mm=Decimal("5"), margin_right_mm=Decimal("5"))
        assert profile.printable_width_mm() == Decimal("290")
        assert profile.printable_height_mm() == Decimal("430")

    def test_standard_12x18_uses_real_conversion(self):
        profile = LoyaltyCardSheetProfile.standard_12x18()
        assert profile.width_mm == Decimal("12") * MM_PER_INCH
        assert profile.height_mm == Decimal("18") * MM_PER_INCH
        assert profile.width_mm == Decimal("304.8")
        assert profile.height_mm == Decimal("457.2")

    def test_deactivate_activate(self):
        profile = LoyaltyCardSheetProfile.standard_12x18()
        profile.deactivate()
        assert not profile.active
        profile.activate()
        assert profile.active


class TestImpositionPolicy:
    def test_simple_grid(self):
        result = ImpositionPolicy.compute(
            printable_width_mm=Decimal("300"), printable_height_mm=Decimal("200"),
            card_width_mm=Decimal("85.6"), card_height_mm=Decimal("54"),
            bleed_mm=Decimal("0"), gutter_horizontal_mm=Decimal("0"),
            gutter_vertical_mm=Decimal("0"))
        assert result.columns == 3
        assert result.rows == 3
        assert result.cards_per_sheet == 9

    def test_bleed_and_gutter_reduce_fit(self):
        no_bleed = ImpositionPolicy.compute(
            printable_width_mm=Decimal("300"), printable_height_mm=Decimal("200"),
            card_width_mm=Decimal("85.6"), card_height_mm=Decimal("54"),
            bleed_mm=Decimal("0"), gutter_horizontal_mm=Decimal("0"),
            gutter_vertical_mm=Decimal("0"))
        with_bleed = ImpositionPolicy.compute(
            printable_width_mm=Decimal("300"), printable_height_mm=Decimal("200"),
            card_width_mm=Decimal("85.6"), card_height_mm=Decimal("54"),
            bleed_mm=Decimal("3"), gutter_horizontal_mm=Decimal("5"),
            gutter_vertical_mm=Decimal("5"))
        assert with_bleed.columns <= no_bleed.columns
        assert with_bleed.rows <= no_bleed.rows

    def test_card_too_big_for_sheet_raises(self):
        with pytest.raises(CardDoesNotFitOnSheetError):
            ImpositionPolicy.compute(
                printable_width_mm=Decimal("50"), printable_height_mm=Decimal("50"),
                card_width_mm=Decimal("85.6"), card_height_mm=Decimal("54"),
                bleed_mm=Decimal("0"), gutter_horizontal_mm=Decimal("0"),
                gutter_vertical_mm=Decimal("0"))


class TestLoyaltyCardImpositionProfile:
    def test_create_computes_columns_and_rows(self):
        profile = LoyaltyCardImpositionProfile.create(
            "sheet-1", printable_width_mm=Decimal("300"), printable_height_mm=Decimal("200"),
            card_width_mm=Decimal("85.6"), card_height_mm=Decimal("54"))
        assert profile.columns == 3
        assert profile.rows == 3
        assert profile.cards_per_sheet == 9

    def test_safe_area_too_large_rejected(self):
        with pytest.raises(InvalidImpositionProfileError):
            LoyaltyCardImpositionProfile.create(
                "sheet-1", printable_width_mm=Decimal("300"), printable_height_mm=Decimal("200"),
                card_width_mm=Decimal("85.6"), card_height_mm=Decimal("54"),
                safe_area_mm=Decimal("30"))

    def test_negative_bleed_rejected(self):
        with pytest.raises(InvalidImpositionProfileError):
            LoyaltyCardImpositionProfile(
                id="x", sheet_profile_id="sheet-1", card_width_mm=Decimal("85.6"),
                card_height_mm=Decimal("54"), columns=1, rows=1, bleed_mm=Decimal("-1"))

    def test_card_does_not_fit_propagates(self):
        with pytest.raises(CardDoesNotFitOnSheetError):
            LoyaltyCardImpositionProfile.create(
                "sheet-1", printable_width_mm=Decimal("10"), printable_height_mm=Decimal("10"),
                card_width_mm=Decimal("85.6"), card_height_mm=Decimal("54"))
