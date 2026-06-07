from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.application.commands.inventory_commands import AdjustInventoryCommand, RegisterInventoryMovementCommand
from backend.application.queries.inventory_query_service import InventoryQueryService
from backend.application.services.inventory_application_service import InventoryApplicationService
from backend.application.use_cases.adjust_inventory_use_case import AdjustInventoryUseCase
from backend.application.use_cases.get_inventory_stock_use_case import GetInventoryStockCommand, GetInventoryStockUseCase
from backend.application.use_cases.register_inventory_movement_use_case import RegisterInventoryMovementUseCase
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository
from backend.shared.events.event_bus import InMemoryEventBus
from backend.shared.events.event_names import EventName


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    importlib.import_module("migrations.standalone.098_canonical_inventory").run(conn)
    return conn


def _service(conn: sqlite3.Connection, bus: InMemoryEventBus | None = None) -> InventoryApplicationService:
    return InventoryApplicationService(repository=InventoryRepository(conn), event_bus=bus or InMemoryEventBus())


def test_query_service_reads_empty_stock_without_legacy_sources() -> None:
    conn = _db()
    query = InventoryQueryService(InventoryRepository(conn))

    stock = query.get_stock(1, 1)

    assert stock.product_id == 1
    assert stock.branch_id == 1
    assert stock.quantity == 0.0
    assert query.list_stock(1) == []


def test_increase_stock_updates_canonical_tables_and_emits_event() -> None:
    conn = _db()
    bus = InMemoryEventBus()
    movement_events = []
    stock_events = []
    bus.subscribe(EventName.INVENTORY_MOVEMENT_RECORDED, movement_events.append)
    bus.subscribe(EventName.INVENTORY_STOCK_UPDATED, stock_events.append)

    result = _service(conn, bus).increase_stock(
        product_id=1,
        branch_id=1,
        quantity=10,
        unit="kg",
        reason="initial count",
        operation_id="op-increase",
        source_module="inventory-test",
        reference_type="TEST",
        reference_id="T-1",
        user_name="ana",
    )

    assert result.success is True
    assert result.stock_before == 0.0
    assert result.stock_after == 10.0
    assert conn.execute("SELECT quantity, unit FROM inventory_stock WHERE product_id=1 AND branch_id=1").fetchone() == (10.0, "kg")
    movement = conn.execute("SELECT operation_id, movement_type, quantity, stock_before, stock_after FROM inventory_movements").fetchone()
    assert movement == ("op-increase", "INCREASE", 10.0, 0.0, 10.0)
    assert [event.event_name for event in result.events] == [
        EventName.INVENTORY_MOVEMENT_RECORDED,
        EventName.INVENTORY_STOCK_UPDATED,
    ]
    assert len(movement_events) == 1
    assert len(stock_events) == 1
    assert movement_events[0].payload["operation_id"] == "op-increase"
    assert movement_events[0].payload["stock_after"] == 10.0
    assert stock_events[0].payload == movement_events[0].payload


def test_inventory_mutation_events_use_required_payload_contract() -> None:
    conn = _db()
    bus = InMemoryEventBus()
    published = []
    bus.subscribe(EventName.INVENTORY_MOVEMENT_RECORDED, published.append)
    bus.subscribe(EventName.INVENTORY_STOCK_UPDATED, published.append)

    result = _service(conn, bus).increase_stock(
        product_id=3,
        branch_id=2,
        quantity=4,
        unit="kg",
        reason="event contract",
        operation_id="op-event-contract",
        source_module="inventory-test",
        reference_type="TEST",
        reference_id="EV-1",
        user_name="ana",
    )

    required_payload_keys = {
        "operation_id",
        "product_id",
        "branch_id",
        "movement_type",
        "quantity",
        "stock_before",
        "stock_after",
        "unit",
        "source_module",
        "reference_type",
        "reference_id",
        "user_name",
        "timestamp",
    }
    assert result.success is True
    assert [event.event_name for event in published] == [
        EventName.INVENTORY_MOVEMENT_RECORDED,
        EventName.INVENTORY_STOCK_UPDATED,
    ]
    for event in published:
        assert required_payload_keys <= set(event.payload)
        assert event.operation_id == "op-event-contract"
        assert event.branch_id == "2"
        assert event.source_module == "inventory-test"
        assert event.payload["product_id"] == 3
        assert event.payload["branch_id"] == 2
        assert event.payload["movement_type"] == "INCREASE"
        assert event.payload["quantity"] == 4.0
        assert event.payload["stock_before"] == 0.0
        assert event.payload["stock_after"] == 4.0
        assert event.payload["unit"] == "kg"
        assert event.payload["reference_type"] == "TEST"
        assert event.payload["reference_id"] == "EV-1"
        assert event.payload["user_name"] == "ana"



def test_decrease_stock_blocks_negative_stock() -> None:
    conn = _db()

    result = _service(conn).decrease_stock(
        product_id=1,
        branch_id=1,
        quantity=1,
        unit="kg",
        reason="sale",
        operation_id="op-negative",
        source_module="inventory-test",
        user_name="ana",
    )

    assert result.success is False
    assert result.message == "INVENTORY_NEGATIVE_STOCK_NOT_ALLOWED"
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 0


def test_adjust_use_case_sets_stock_and_get_use_case_reads_it() -> None:
    conn = _db()
    repository = InventoryRepository(conn)
    service = _service(conn)

    adjust_result = AdjustInventoryUseCase(service).execute(AdjustInventoryCommand(
        operation_id="op-adjust",
        branch_id="2",
        user_name="ana",
        product_id=1,
        new_quantity=7,
        unit="kg",
        reason="physical count",
        source_module="inventory-test",
    ))
    stock_result = GetInventoryStockUseCase(InventoryQueryService(repository)).execute(
        GetInventoryStockCommand(operation_id="op-read", product_id=1, branch_id=2)
    )

    assert adjust_result.success is True
    assert stock_result.success is True
    assert stock_result.data["quantity"] == 7.0


def test_register_movement_use_case_is_idempotent_by_operation_product_branch_type() -> None:
    conn = _db()
    use_case = RegisterInventoryMovementUseCase(_service(conn))
    command = RegisterInventoryMovementCommand(
        operation_id="op-idempotent",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=5,
        unit="kg",
        movement_type="INCREASE",
        source_module="inventory-test",
    )

    first = use_case.execute(command)
    second = use_case.execute(command)

    assert first.success is True
    assert second.success is True
    assert conn.execute("SELECT quantity FROM inventory_stock WHERE product_id=1 AND branch_id=1").fetchone()[0] == 5.0
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 1


def test_transfer_stock_moves_between_branches() -> None:
    conn = _db()
    service = _service(conn)
    service.increase_stock(1, 1, 10, "kg", "seed", "op-seed", "inventory-test", user_name="ana")

    result = service.transfer_stock(
        product_id=1,
        from_branch_id=1,
        to_branch_id=2,
        quantity=4,
        unit="kg",
        reason="branch transfer",
        operation_id="op-transfer",
        source_module="inventory-test",
        user_name="ana",
    )

    query = InventoryQueryService(InventoryRepository(conn))
    assert result.success is True
    assert query.get_stock(1, 1).quantity == 6.0
    assert query.get_stock(1, 2).quantity == 4.0
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements WHERE operation_id='op-transfer'").fetchone()[0] == 2


def test_command_validation_requires_context() -> None:
    with pytest.raises(ValueError):
        RegisterInventoryMovementCommand(
            operation_id="",
            branch_id="1",
            user_name="ana",
            product_id=1,
            quantity=1,
            movement_type="INCREASE",
        ).validate_context()
