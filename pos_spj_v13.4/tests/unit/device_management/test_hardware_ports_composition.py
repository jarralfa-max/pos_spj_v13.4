"""SET-10 — "Gateways": CashDrawerGatewayPort/PaymentTerminalGatewayPort
composition. These are Protocols with no real implementation in this
bounded context (see hardware_ports.py's docstring — actual serial/
network I/O is a later SET's infrastructure job); this test proves the
shape works end to end with a fake gateway, the same way SET-8's
`test_configuration_cache_service.py::TestCacheResolutionComposition`
documented cache+resolution composition without a real cache backend.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.exceptions import CashDrawerOpeningNotAuthorizedError
from backend.domain.device_management.hardware_ports import (
    CashDrawerGatewayPort,
    PaymentTerminalGatewayPort,
)
from backend.domain.device_management.policies.cash_drawer_security_policy import assert_can_open
from backend.domain.device_management.value_objects.cash_drawer_open_request import CashDrawerOpenRequest
from backend.shared.ids import new_uuid


class _FakeCashDrawerGateway:
    """Satisfies CashDrawerGatewayPort structurally — no real hardware."""

    def __init__(self) -> None:
        self.opened_devices: list[str] = []

    def open(self, request: CashDrawerOpenRequest) -> bool:
        self.opened_devices.append(request.device_id)
        return True

    def is_open(self, device_id: str) -> bool:
        return device_id in self.opened_devices


class _FakePaymentTerminalGateway:
    def __init__(self, *, ready: bool = True) -> None:
        self._ready = ready

    def is_ready(self, device_id: str) -> bool:
        return self._ready


def _open_drawer_use_case(gateway: CashDrawerGatewayPort, request: CashDrawerOpenRequest) -> bool:
    """The shape a future application-layer use case follows: authorize
    first (domain policy), only then touch the gateway (infrastructure)."""
    assert_can_open(request)
    return gateway.open(request)


class TestCashDrawerGatewayComposition:
    def test_authorized_open_reaches_the_gateway(self):
        gateway = _FakeCashDrawerGateway()
        device_id = new_uuid()
        request = CashDrawerOpenRequest.create(
            device_id=device_id, opened_by_user_id="cashier-1", sale_reference="SALE-001",
        )
        assert _open_drawer_use_case(gateway, request) is True
        assert gateway.is_open(device_id) is True

    def test_unauthorized_open_never_reaches_the_gateway(self):
        gateway = _FakeCashDrawerGateway()
        device_id = new_uuid()
        request = CashDrawerOpenRequest.create(device_id=device_id, opened_by_user_id="cashier-1")
        with pytest.raises(CashDrawerOpeningNotAuthorizedError):
            _open_drawer_use_case(gateway, request)
        assert gateway.is_open(device_id) is False
        assert gateway.opened_devices == []


class TestPaymentTerminalGatewayComposition:
    def test_ready_terminal_reports_ready(self):
        gateway: PaymentTerminalGatewayPort = _FakePaymentTerminalGateway(ready=True)
        assert gateway.is_ready(new_uuid()) is True

    def test_not_ready_terminal_reports_not_ready(self):
        gateway: PaymentTerminalGatewayPort = _FakePaymentTerminalGateway(ready=False)
        assert gateway.is_ready(new_uuid()) is False
