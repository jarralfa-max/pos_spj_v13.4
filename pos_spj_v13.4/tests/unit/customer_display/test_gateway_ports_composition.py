"""SET-17 — "Gateway": CustomerDisplayGatewayPort composition +
display_state_push_policy.push_state. A Protocol with no real
implementation in this bounded context (see gateway_ports.py's docstring
— no real customer-display hardware exists anywhere in this repository);
this test proves the shape works end to end with a fake gateway,
mirroring
tests/unit/document_output/test_rendering_ports_composition.py's pattern.
"""

from __future__ import annotations

import pytest

from backend.domain.customer_display.entities.customer_display import CustomerDisplay
from backend.domain.customer_display.entities.display_layout import DisplayLayout
from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.gateway_ports import CustomerDisplayGatewayPort
from backend.domain.customer_display.policies.display_state_push_policy import push_state
from backend.domain.customer_display.value_objects.display_section import DisplaySection
from backend.shared.ids import new_uuid


class _FakeGateway:
    """Satisfies CustomerDisplayGatewayPort structurally — no real hardware."""

    def __init__(self) -> None:
        self.pushed: list[dict] = []

    def push(self, *, display_id: str, mode: CustomerDisplayMode, content: dict) -> None:
        self.pushed.append({"display_id": display_id, "mode": mode, "content": content})


class _FailingGateway:
    def push(self, *, display_id: str, mode: CustomerDisplayMode, content: dict) -> None:
        raise ConnectionError("pantalla no disponible")


def _display() -> CustomerDisplay:
    return CustomerDisplay.create(workstation_id=new_uuid(), name="Pantalla Caja 1")


def _cart_layout() -> DisplayLayout:
    return DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[
        DisplaySection.create(code=CustomerDisplaySectionCode.CUSTOMER_NAME, order=0),
        DisplaySection.create(code=CustomerDisplaySectionCode.ITEMS, order=1),
        DisplaySection.create(code=CustomerDisplaySectionCode.TOTAL, order=2),
        DisplaySection.create(code=CustomerDisplaySectionCode.LOGO, order=3, enabled=False),
    ])


class TestPushStateComposition:
    def test_content_is_filtered_to_enabled_section_codes(self):
        gateway: CustomerDisplayGatewayPort = _FakeGateway()
        display = _display()
        layout = _cart_layout()
        content = {
            "CUSTOMER_NAME": "Juan Pérez", "ITEMS": ["Carne molida"], "TOTAL": "245.00",
            "LOGO": "base64...", "SUBTOTAL": "245.00",
        }
        push_state(gateway, display=display, layout=layout, content=content)

        pushed = gateway.pushed[0]
        assert pushed["display_id"] == display.id
        assert pushed["mode"] is CustomerDisplayMode.CART
        assert pushed["content"] == {
            "CUSTOMER_NAME": "Juan Pérez", "ITEMS": ["Carne molida"], "TOTAL": "245.00",
        }

    def test_missing_content_keys_are_simply_absent_not_errors(self):
        gateway: CustomerDisplayGatewayPort = _FakeGateway()
        push_state(gateway, display=_display(), layout=_cart_layout(), content={"TOTAL": "0.00"})
        assert gateway.pushed[0]["content"] == {"TOTAL": "0.00"}

    def test_gateway_failure_propagates(self):
        with pytest.raises(ConnectionError):
            push_state(_FailingGateway(), display=_display(), layout=_cart_layout(), content={})
