"""SET-10 — CashDrawerOpenRequest + CashDrawerSecurityPolicy: the
"apertura sin venta requiere motivo" anti-theft control (§60, traceable
to the legacy `CASH_DRAWER_OPEN_WITHOUT_SALE` permission). Pure domain
— no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.exceptions import (
    CashDrawerOpeningNotAuthorizedError,
    DeviceInvalidValueError,
)
from backend.domain.device_management.policies.cash_drawer_security_policy import assert_can_open
from backend.domain.device_management.value_objects.cash_drawer_open_request import CashDrawerOpenRequest
from backend.shared.ids import new_uuid


def _request(**overrides) -> CashDrawerOpenRequest:
    kwargs = dict(device_id=new_uuid(), opened_by_user_id="cashier-1")
    kwargs.update(overrides)
    return CashDrawerOpenRequest.create(**kwargs)


class TestCashDrawerOpenRequestCreate:
    def test_validates_device_id(self):
        with pytest.raises(ValueError):
            CashDrawerOpenRequest.create(device_id="not-a-uuid", opened_by_user_id="cashier-1")

    def test_requires_opened_by_user_id(self):
        with pytest.raises(DeviceInvalidValueError):
            _request(opened_by_user_id="   ")

    def test_no_sale_and_no_reason_is_a_well_formed_request(self):
        # Shape validity and authorization are deliberately separate —
        # CashDrawerOpenRequest.create() doesn't reject this; only
        # assert_can_open() does (see below).
        request = _request(sale_reference=None, reason=None)
        assert request.is_linked_to_sale() is False

    def test_is_linked_to_sale_reflects_sale_reference(self):
        assert _request(sale_reference="SALE-001").is_linked_to_sale() is True
        assert _request(sale_reference=None).is_linked_to_sale() is False

    def test_strips_whitespace_from_sale_reference_and_reason(self):
        request = _request(sale_reference="  SALE-001  ", reason="  turno  ")
        assert request.sale_reference == "SALE-001"
        assert request.reason == "turno"


class TestAssertCanOpen:
    def test_linked_to_sale_requires_no_reason(self):
        assert_can_open(_request(sale_reference="SALE-001"))

    def test_no_sale_and_no_reason_is_denied(self):
        with pytest.raises(CashDrawerOpeningNotAuthorizedError):
            assert_can_open(_request(sale_reference=None, reason=None))

    def test_no_sale_but_with_reason_is_allowed(self):
        assert_can_open(_request(sale_reference=None, reason="Conteo de cambio de turno"))

    def test_both_sale_and_reason_present_is_allowed(self):
        assert_can_open(_request(sale_reference="SALE-001", reason="Confirmación adicional"))

    def test_empty_string_reason_does_not_count_as_a_reason(self):
        # CashDrawerOpenRequest.create() already normalizes "" -> None,
        # but assert_can_open must not be fooled if a caller somehow
        # constructs the dataclass directly with whitespace.
        request = CashDrawerOpenRequest(device_id=new_uuid(), opened_by_user_id="cashier-1", reason="   ")
        with pytest.raises(CashDrawerOpeningNotAuthorizedError):
            assert_can_open(request)
