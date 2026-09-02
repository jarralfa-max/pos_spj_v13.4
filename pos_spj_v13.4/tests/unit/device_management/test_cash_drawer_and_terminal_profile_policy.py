"""SET-10 — CashDrawerProfilePolicy + PaymentTerminalProfilePolicy
(§18/§20/§23). Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import (
    CASH_DRAWER_DEVICE_TYPES,
    PAYMENT_TERMINAL_CAPABILITIES,
    PAYMENT_TERMINAL_DEVICE_TYPES,
    ConnectionType,
    DeviceCapabilityCode,
    DeviceType,
)
from backend.domain.device_management.exceptions import (
    InvalidCashDrawerProfileError,
    InvalidPaymentTerminalProfileError,
)
from backend.domain.device_management.policies.cash_drawer_profile_policy import (
    assert_valid_cash_drawer_profile,
)
from backend.domain.device_management.policies.payment_terminal_profile_policy import (
    assert_valid_payment_terminal_profile,
)
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.device_capability import DeviceCapability

_USB = ConnectionProfile.create(ConnectionType.USB)


def _drawer_profile(**overrides) -> DeviceProfile:
    kwargs = dict(
        name="MMF Cajón", device_type=DeviceType.CASH_DRAWER, connection_profile=_USB,
        capabilities=(DeviceCapability.create(DeviceCapabilityCode.DRAWER_PULSE),),
    )
    kwargs.update(overrides)
    return DeviceProfile.create(**kwargs)


def _terminal_profile(**overrides) -> DeviceProfile:
    kwargs = dict(
        name="Clip Terminal", device_type=DeviceType.PAYMENT_TERMINAL, connection_profile=_USB,
        capabilities=(DeviceCapability.create(DeviceCapabilityCode.CARD_CONTACTLESS),),
    )
    kwargs.update(overrides)
    return DeviceProfile.create(**kwargs)


class TestCashDrawerProfilePolicy:
    def test_valid_profile_passes(self):
        assert_valid_cash_drawer_profile(_drawer_profile())

    @pytest.mark.parametrize("device_type", [t for t in DeviceType if t not in CASH_DRAWER_DEVICE_TYPES])
    def test_non_cash_drawer_device_types_rejected(self, device_type):
        with pytest.raises(InvalidCashDrawerProfileError):
            assert_valid_cash_drawer_profile(_drawer_profile(device_type=device_type))

    def test_missing_drawer_pulse_capability_rejected(self):
        profile = DeviceProfile.create(name="Sin pulso", device_type=DeviceType.CASH_DRAWER, connection_profile=_USB)
        with pytest.raises(InvalidCashDrawerProfileError):
            assert_valid_cash_drawer_profile(profile)


class TestPaymentTerminalProfilePolicy:
    def test_valid_profile_passes(self):
        assert_valid_payment_terminal_profile(_terminal_profile())

    @pytest.mark.parametrize("device_type", [t for t in DeviceType if t not in PAYMENT_TERMINAL_DEVICE_TYPES])
    def test_non_terminal_device_types_rejected(self, device_type):
        with pytest.raises(InvalidPaymentTerminalProfileError):
            assert_valid_payment_terminal_profile(_terminal_profile(device_type=device_type))

    def test_any_single_payment_capability_is_sufficient(self):
        for capability_code in PAYMENT_TERMINAL_CAPABILITIES:
            profile = _terminal_profile(capabilities=(DeviceCapability.create(capability_code),))
            assert_valid_payment_terminal_profile(profile)

    def test_no_payment_capability_rejected(self):
        profile = DeviceProfile.create(
            name="Sin capacidad de pago", device_type=DeviceType.PAYMENT_TERMINAL, connection_profile=_USB,
        )
        with pytest.raises(InvalidPaymentTerminalProfileError):
            assert_valid_payment_terminal_profile(profile)

    def test_unrelated_capability_alone_is_not_sufficient(self):
        # Declaring e.g. CUT (a printer capability) doesn't make a device
        # a working payment terminal.
        profile = _terminal_profile(capabilities=(DeviceCapability.create(DeviceCapabilityCode.CUT),))
        with pytest.raises(InvalidPaymentTerminalProfileError):
            assert_valid_payment_terminal_profile(profile)
