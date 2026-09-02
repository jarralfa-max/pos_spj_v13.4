"""SET-17 — "Displays": CustomerDisplay entity. Pure domain — no DB."""

from __future__ import annotations

import pytest

from backend.domain.customer_display.entities.customer_display import CustomerDisplay
from backend.domain.customer_display.enums import CustomerDisplayMode
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.shared.ids import is_uuidv7, new_uuid


def _display(**overrides) -> CustomerDisplay:
    kwargs = dict(workstation_id=new_uuid(), name="Pantalla Caja 1")
    kwargs.update(overrides)
    return CustomerDisplay.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_and_defaults_to_idle(self):
        display = _display()
        assert is_uuidv7(display.id)
        assert display.current_mode is CustomerDisplayMode.IDLE
        assert display.active is True

    def test_validates_workstation_id_as_uuid(self):
        with pytest.raises(ValueError):
            _display(workstation_id="not-a-uuid")

    def test_requires_name(self):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _display(name="   ")

    def test_trims_name(self):
        display = _display(name="  Pantalla Caja 1  ")
        assert display.name == "Pantalla Caja 1"


class TestActivateDeactivate:
    def test_activate_deactivate(self):
        display = _display()
        display.deactivate()
        assert display.active is False
        display.activate()
        assert display.active is True


class TestSetMode:
    @pytest.mark.parametrize(
        "mode", [CustomerDisplayMode.CART, CustomerDisplayMode.PAYMENT_PENDING, CustomerDisplayMode.THANK_YOU, CustomerDisplayMode.IDLE],
    )
    def test_set_mode_is_unconstrained(self, mode):
        display = _display()
        display.set_mode(mode)
        assert display.current_mode is mode

    def test_mode_can_change_any_number_of_times(self):
        display = _display()
        for mode in (
            CustomerDisplayMode.CART, CustomerDisplayMode.PAYMENT_PENDING, CustomerDisplayMode.THANK_YOU,
            CustomerDisplayMode.IDLE, CustomerDisplayMode.CART,
        ):
            display.set_mode(mode)
            assert display.current_mode is mode
