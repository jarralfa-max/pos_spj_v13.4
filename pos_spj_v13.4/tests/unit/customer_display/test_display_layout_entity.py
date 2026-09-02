"""SET-17 — "Layouts": DisplayLayout entity + DisplaySection. Pure
domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.customer_display.entities.display_layout import DisplayLayout
from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.domain.customer_display.value_objects.display_section import DisplaySection
from backend.shared.ids import is_uuidv7


def _section(**overrides) -> DisplaySection:
    kwargs = dict(code=CustomerDisplaySectionCode.ITEMS, order=0)
    kwargs.update(overrides)
    return DisplaySection.create(**kwargs)


class TestDisplaySectionCreate:
    def test_defaults_to_enabled(self):
        section = _section()
        assert section.enabled is True

    @pytest.mark.parametrize("order", [-1, 1.5, True])
    def test_rejects_invalid_order(self, order):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _section(order=order)


class TestDisplayLayoutCreate:
    def test_mints_uuidv7(self):
        layout = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[_section()])
        assert is_uuidv7(layout.id)
        assert layout.active is True

    def test_requires_at_least_one_section(self):
        with pytest.raises(CustomerDisplayInvalidValueError):
            DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[])

    def test_rejects_duplicate_section_codes(self):
        with pytest.raises(CustomerDisplayInvalidValueError):
            DisplayLayout.create(
                mode=CustomerDisplayMode.CART,
                sections=[_section(order=0), _section(order=1)],
            )


class TestDisplayLayoutActivateDeactivate:
    def test_activate_deactivate(self):
        layout = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[_section()])
        layout.deactivate()
        assert layout.active is False
        layout.activate()
        assert layout.active is True


class TestDisplayLayoutQueries:
    def _layout(self) -> DisplayLayout:
        return DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[
            DisplaySection.create(code=CustomerDisplaySectionCode.TOTAL, order=2),
            DisplaySection.create(code=CustomerDisplaySectionCode.CUSTOMER_NAME, order=0),
            DisplaySection.create(code=CustomerDisplaySectionCode.ITEMS, order=1, enabled=False),
        ])

    def test_ordered_sections_sorts_by_order(self):
        layout = self._layout()
        assert [s.code for s in layout.ordered_sections()] == [
            CustomerDisplaySectionCode.CUSTOMER_NAME, CustomerDisplaySectionCode.ITEMS,
            CustomerDisplaySectionCode.TOTAL,
        ]

    def test_enabled_codes_skips_disabled_and_preserves_order(self):
        layout = self._layout()
        assert layout.enabled_codes() == (
            CustomerDisplaySectionCode.CUSTOMER_NAME, CustomerDisplaySectionCode.TOTAL,
        )
