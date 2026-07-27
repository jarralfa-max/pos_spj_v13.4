from __future__ import annotations

from backend.application.commands.inventory_commands import (
    AdjustInventoryCommand,
    RegisterInventoryEntryCommand,
)
from backend.application.services.inventory_application_service import InventoryApplicationService


class FakeInventoryService:
    def __init__(self) -> None:
        self.stock = 5.0
        self.calls = []

    def get_stock(self, product_id: int, branch_id: int) -> float:
        return self.stock

    def add_stock(self, **kwargs) -> None:
        self.calls.append(("add", kwargs))
        self.stock += float(kwargs["qty"])

    def deduct_stock(self, **kwargs) -> None:
        self.calls.append(("deduct", kwargs))
        self.stock -= float(kwargs["qty"])


class FakeDb:
    def __init__(self) -> None:
        self.committed = False

    def execute(self, *args, **kwargs):
        raise RuntimeError("audit tables are optional in this protection test")

    def commit(self) -> None:
        self.committed = True


class FakeEventBus:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event, payload, async_=False) -> None:
        self.events.append((event, payload, async_))


def test_register_entry_preserves_stock_update_and_operation_event_payload() -> None:
    inv = FakeInventoryService()
    bus = FakeEventBus()
    service = InventoryApplicationService(db=FakeDb(), inventory_service=inv, event_bus=bus)

    result = service.register_entry(
        RegisterInventoryEntryCommand(
            operation_id="UI-OP-1",
            branch_id=1,
            user_name="almacen",
            product_id=7,
            quantity=3.5,
            unit_cost=12.0,
            notes="recepción manual",
        )
    )

    assert result.ok is True
    assert result.stock_nuevo == 8.5
    assert inv.calls[0][0] == "add"
    assert inv.calls[0][1]["operation_id"] == result.operacion_id
    assert bus.events[0][1]["operation_id"] == result.operacion_id


def test_adjust_stock_preserves_delta_deduction_and_operation_event_payload() -> None:
    inv = FakeInventoryService()
    bus = FakeEventBus()
    service = InventoryApplicationService(db=FakeDb(), inventory_service=inv, event_bus=bus)

    result = service.adjust_stock(
        AdjustInventoryCommand(
            operation_id="UI-OP-2",
            branch_id=1,
            user_name="auditor",
            product_id=7,
            new_quantity=2.0,
            reason="Conteo físico — prueba",
        )
    )

    assert result.ok is True
    assert result.stock_nuevo == 2.0
    assert inv.calls[0][0] == "deduct"
    assert inv.calls[0][1]["qty"] == 3.0
    assert inv.calls[0][1]["operation_id"] == result.operacion_id
    assert bus.events[0][1]["operation_id"] == result.operacion_id
