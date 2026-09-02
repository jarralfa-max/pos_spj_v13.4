# tests/test_domain_whatsapp_numbers.py — WA-2
"""WhatsAppChannelNumber y WhatsAppPhoneNumber."""
from __future__ import annotations

import pytest

from domain.whatsapp.entities.channel_number import WhatsAppChannelNumber
from domain.whatsapp.enums import ChannelNumberStatus, ChannelRole
from domain.whatsapp.exceptions import InvalidChannelNumberStateError, InvalidPhoneNumberError
from domain.whatsapp.value_objects.phone_number import WhatsAppPhoneNumber


def _number(**overrides):
    defaults = dict(
        account_id="acc-1",
        phone_number_external_id="ext-1",
        display_phone_number="5512345678",
        channel_role=ChannelRole.BRANCH_SALES,
        branch_id="branch-1",
    )
    defaults.update(overrides)
    return WhatsAppChannelNumber.create(**defaults)


class TestWhatsAppPhoneNumber:
    def test_normalizes_mx_10_digit_to_e164(self):
        assert WhatsAppPhoneNumber.from_raw("5512345678").value == "+525512345678"

    def test_normalizes_already_e164(self):
        assert WhatsAppPhoneNumber.from_raw("+525512345678").value == "+525512345678"

    def test_normalizes_whatsapp_prefixed(self):
        assert WhatsAppPhoneNumber.from_raw("whatsapp:+525512345678").value == "+525512345678"

    def test_rejects_empty(self):
        with pytest.raises(InvalidPhoneNumberError):
            WhatsAppPhoneNumber.from_raw("")

    def test_is_immutable(self):
        phone = WhatsAppPhoneNumber.from_raw("5512345678")
        with pytest.raises(Exception):
            phone.value = "+520000000000"  # type: ignore[misc]

    def test_str_returns_value(self):
        phone = WhatsAppPhoneNumber.from_raw("5512345678")
        assert str(phone) == "+525512345678"


class TestWhatsAppChannelNumberCreate:
    def test_starts_in_draft(self):
        assert _number().status == ChannelNumberStatus.DRAFT

    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7
        assert is_uuidv7(_number().id)

    def test_normalized_phone_is_e164(self):
        number = _number(display_phone_number="5512345678")
        assert number.normalized_phone_number.value == "+525512345678"

    def test_branch_role_requires_branch_id(self):
        with pytest.raises(ValueError):
            _number(channel_role=ChannelRole.BRANCH_SALES, branch_id=None)

    def test_delivery_role_requires_branch_id(self):
        with pytest.raises(ValueError):
            _number(channel_role=ChannelRole.DELIVERY, branch_id=None)

    def test_global_role_does_not_require_branch_id(self):
        number = _number(channel_role=ChannelRole.GLOBAL_CUSTOMER_SERVICE, branch_id=None)
        assert number.branch_id is None
        assert number.is_global() is True

    def test_rejects_invalid_phone(self):
        with pytest.raises(InvalidPhoneNumberError):
            _number(display_phone_number="")


class TestWhatsAppChannelNumberLifecycle:
    def test_activate_then_usable(self):
        number = _number()
        number.activate()
        assert number.status == ChannelNumberStatus.ACTIVE
        assert number.is_usable() is True

    def test_degraded_is_still_usable(self):
        number = _number()
        number.activate()
        number.mark_degraded()
        assert number.is_usable() is True

    def test_suspended_is_not_usable(self):
        number = _number()
        number.activate()
        number.suspend()
        assert number.is_usable() is False

    def test_retired_number_cannot_be_reactivated(self):
        number = _number()
        number.retire()
        with pytest.raises(InvalidChannelNumberStateError):
            number.activate()

    def test_retired_number_cannot_be_suspended(self):
        number = _number()
        number.retire()
        with pytest.raises(InvalidChannelNumberStateError):
            number.suspend()
