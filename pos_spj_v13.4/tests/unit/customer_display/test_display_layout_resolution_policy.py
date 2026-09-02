"""SET-17 — "Modes": display_layout_resolution_policy.resolve_layout.
Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.customer_display.entities.display_layout import DisplayLayout
from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.exceptions import DisplayLayoutNotFoundError
from backend.domain.customer_display.policies.display_layout_resolution_policy import resolve_layout
from backend.domain.customer_display.value_objects.display_section import DisplaySection


def _layout(mode: CustomerDisplayMode) -> DisplayLayout:
    return DisplayLayout.create(
        mode=mode, sections=[DisplaySection.create(code=CustomerDisplaySectionCode.MESSAGE, order=0)],
    )


class TestResolveLayout:
    def test_finds_the_active_layout_for_the_mode(self):
        cart = _layout(CustomerDisplayMode.CART)
        idle = _layout(CustomerDisplayMode.IDLE)
        resolved = resolve_layout([cart, idle], CustomerDisplayMode.CART)
        assert resolved is cart

    def test_raises_when_no_layout_matches_the_mode(self):
        idle = _layout(CustomerDisplayMode.IDLE)
        with pytest.raises(DisplayLayoutNotFoundError):
            resolve_layout([idle], CustomerDisplayMode.THANK_YOU)

    def test_inactive_layouts_are_ignored(self):
        cart = _layout(CustomerDisplayMode.CART)
        cart.deactivate()
        with pytest.raises(DisplayLayoutNotFoundError):
            resolve_layout([cart], CustomerDisplayMode.CART)

    def test_raises_on_empty_candidate_list(self):
        with pytest.raises(DisplayLayoutNotFoundError):
            resolve_layout([], CustomerDisplayMode.CART)
