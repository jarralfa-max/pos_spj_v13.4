from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

from backend.application.commands.waste_commands import RegisterWasteCommand
from backend.application.queries.inventory_query_service import InventoryQueryService
from backend.application.services.inventory_application_service import InventoryApplicationService
from backend.application.services.waste_application_service import WasteApplicationService
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository
from backend.infrastructure.db.repositories.waste_repository import WasteRepository
from backend.shared.events.event_bus import InMemoryEventBus
from backend.shared.events.event_names import EventName

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio_compra REAL,
            unidad TEXT,
            existencia REAL,
            activo INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE mermas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER NOT NULL,
            cantidad REAL NOT NULL,
            unidad TEXT,
            motivo TEXT,
            costo_unitario REAL,
            valor_perdida REAL,
            notas TEXT,
            usuario TEXT,
            operation_id TEXT,
            created_at TEXT,
            fecha TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER NOT NULL,
            cantidad REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE branch_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            cantidad REAL,
            operation_id TEXT
        )
        """
    )
    importlib.import_module("migrations.standalone.098_canonical_inventory").run(conn)
    conn.execute(
        "INSERT INTO productos(id, nombre, precio_compra, unidad, existencia, activo) VALUES (1, 'Arrachera', 100, 'kg', 999, 1)"
    )
    conn.execute("INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad) VALUES (1, 1, 88)")
    conn.execute("INSERT INTO branch_inventory(product_id, branch_id, quantity) VALUES (1, 1, 77)")
    conn.commit()
    return conn


def _inventory_service(conn: sqlite3.Connection, bus: InMemoryEventBus | None = None) -> InventoryApplicationService:
    return InventoryApplicationService(repository=InventoryRepository(conn), event_bus=bus or InMemoryEventBus())


def _inventory_query(conn: sqlite3.Connection) -> InventoryQueryService:
    return InventoryQueryService(InventoryRepository(conn))


def _waste_service(conn: sqlite3.Connection, bus: InMemoryEventBus | None = None) -> WasteApplicationService:
    return WasteApplicationService(
        repository=WasteRepository(conn),
        inventory_service=_inventory_service(conn, bus),
        event_bus=bus,
    )


def test_phase8_inventory_stock_starts_per_product_and_branch() -> None:
    conn = _db()
    query = _inventory_query(conn)

    stock = query.get_stock(product_id=1, branch_id=1)

    assert stock.product_id == 1
    assert stock.branch_id == 1
    assert stock.quantity == 0.0
    assert stock.unit == "unit"
    assert query.list_stock(branch_id=1) == []


def test_phase8_increase_stock_adds_exact_quantity_and_records_movement_and_event() -> None:
    conn = _db()
    bus = InMemoryEventBus()
    stock_events = []
    bus.subscribe(EventName.INVENTORY_STOCK_UPDATED, stock_events.append)

    result = _inventory_service(conn, bus).increase_stock(
        product_id=1,
        branch_id=1,
        quantity=10,
        unit="kg",
        reason="initial functional stock",
        operation_id="phase8-increase",
        source_module="phase8-test",
        reference_type="TEST",
        reference_id="INC-1",
        user_name="ana",
    )

    assert result.success is True
    assert result.stock_before == 0.0
    assert result.stock_after == 10.0
    assert _inventory_query(conn).get_stock(1, 1).quantity == 10.0
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements WHERE operation_id='phase8-increase'").fetchone()[0] == 1
    assert len(stock_events) == 1
    assert stock_events[0].payload["stock_after"] == 10.0


def test_phase8_decrease_stock_subtracts_exact_quantity_and_blocks_negative_stock() -> None:
    conn = _db()
    service = _inventory_service(conn)
    service.increase_stock(1, 1, 10, "kg", "seed", "phase8-seed", "phase8-test", user_name="ana")

    decrease = service.decrease_stock(1, 1, 3, "kg", "usage", "phase8-decrease", "phase8-test", user_name="ana")
    negative = service.decrease_stock(1, 1, 8, "kg", "too much", "phase8-negative", "phase8-test", user_name="ana")

    assert decrease.success is True
    assert decrease.stock_before == 10.0
    assert decrease.stock_after == 7.0
    assert negative.success is False
    assert negative.message == "INVENTORY_NEGATIVE_STOCK_NOT_ALLOWED"
    assert _inventory_query(conn).get_stock(1, 1).quantity == 7.0
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements WHERE operation_id='phase8-negative'").fetchone()[0] == 0


def test_phase8_adjust_stock_records_quantity_difference() -> None:
    conn = _db()
    service = _inventory_service(conn)
    service.increase_stock(1, 1, 10, "kg", "seed", "phase8-adjust-seed", "phase8-test", user_name="ana")

    result = service.adjust_stock(1, 1, 6, "kg", "physical count", "phase8-adjust", "phase8-test", user_name="ana")
    movement = conn.execute(
        """
        SELECT movement_type, quantity, stock_before, stock_after
        FROM inventory_movements
        WHERE operation_id='phase8-adjust'
        """
    ).fetchone()

    assert result.success is True
    assert result.stock_before == 10.0
    assert result.stock_after == 6.0
    assert movement == ("ADJUST_DECREASE", 4.0, 10.0, 6.0)
    assert _inventory_query(conn).get_stock(1, 1).quantity == 6.0


def test_phase8_transfer_stock_moves_between_branches_and_records_two_movements() -> None:
    conn = _db()
    service = _inventory_service(conn)
    service.increase_stock(1, 1, 10, "kg", "seed", "phase8-transfer-seed", "phase8-test", user_name="ana")

    result = service.transfer_stock(1, 1, 2, 4, "kg", "transfer", "phase8-transfer", "phase8-test", user_name="ana")

    query = _inventory_query(conn)
    assert result.success is True
    assert query.get_stock(1, 1).quantity == 6.0
    assert query.get_stock(1, 2).quantity == 4.0
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements WHERE operation_id='phase8-transfer'").fetchone()[0] == 2


def test_phase8_waste_one_over_stock_ten_leaves_stock_nine_and_emits_events() -> None:
    conn = _db()
    bus = InMemoryEventBus()
    inventory_events = []
    waste_events = []
    bus.subscribe(EventName.INVENTORY_MOVEMENT_RECORDED, inventory_events.append)
    bus.subscribe(EventName.INVENTORY_STOCK_UPDATED, inventory_events.append)
    bus.subscribe(EventName.WASTE_REGISTERED, waste_events.append)
    _inventory_service(conn).increase_stock(1, 1, 10, "kg", "seed", "phase8-waste-seed", "phase8-test", user_name="ana")

    result = _waste_service(conn, bus).register(RegisterWasteCommand(
        operation_id="phase8-waste-one",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=1,
        unit="kg",
        reason="Merma funcional",
        date="2026-06-08",
    ))

    assert result.success is True
    assert result.data["stock_before"] == 10.0
    assert result.data["stock_after"] == 9.0
    assert _inventory_query(conn).get_stock(1, 1).quantity == 9.0
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements WHERE operation_id='phase8-waste-one'").fetchone()[0] == 1
    assert [event.event_name for event in inventory_events] == [
        EventName.INVENTORY_MOVEMENT_RECORDED,
        EventName.INVENTORY_STOCK_UPDATED,
    ]
    assert len(waste_events) == 1


def test_phase8_waste_does_not_touch_product_existence_or_legacy_inventory_tables() -> None:
    conn = _db()
    _inventory_service(conn).increase_stock(1, 1, 10, "kg", "seed", "phase8-legacy-seed", "phase8-test", user_name="ana")

    result = _waste_service(conn).register(RegisterWasteCommand(
        operation_id="phase8-legacy-untouched",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=2,
        unit="kg",
        reason="Merma funcional legacy",
        date="2026-06-08",
    ))

    assert result.success is True
    assert conn.execute("SELECT existencia FROM productos WHERE id=1").fetchone()[0] == 999.0
    assert conn.execute("SELECT cantidad FROM inventario_actual WHERE producto_id=1 AND sucursal_id=1").fetchone()[0] == 88.0
    assert conn.execute("SELECT quantity FROM branch_inventory WHERE product_id=1 AND branch_id=1").fetchone()[0] == 77.0
    assert conn.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0] == 0


def test_phase8_multi_branch_waste_does_not_affect_other_branch() -> None:
    conn = _db()
    service = _inventory_service(conn)
    service.increase_stock(1, 1, 10, "kg", "seed branch 1", "phase8-multi-seed-1", "phase8-test", user_name="ana")
    service.increase_stock(1, 2, 5, "kg", "seed branch 2", "phase8-multi-seed-2", "phase8-test", user_name="ana")

    result = _waste_service(conn).register(RegisterWasteCommand(
        operation_id="phase8-multi-waste",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=1,
        unit="kg",
        reason="Merma multi sucursal",
        date="2026-06-08",
    ))

    query = _inventory_query(conn)
    assert result.success is True
    assert query.get_stock(1, 1).quantity == 9.0
    assert query.get_stock(1, 2).quantity == 5.0


def test_phase8_no_inventory_sql_in_ui_modules() -> None:
    ui_files = [
        PACKAGE_ROOT / "modulos" / "merma.py",
        PACKAGE_ROOT / "modulos" / "inventario_local.py",
    ]
    forbidden = [
        "inventory_stock",
        "inventory_movements",
        "inventario_actual",
        "branch_inventory",
        "movimientos_inventario",
        "UPDATE productos SET existencia",
        "INSERT INTO inventario_actual",
        "UPDATE inventario_actual",
        "INSERT INTO branch_inventory",
        "UPDATE branch_inventory",
    ]
    violations = {
        str(path.relative_to(PACKAGE_ROOT)): [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for path in ui_files
    }
    assert {path: tokens for path, tokens in violations.items() if tokens} == {}


def test_phase8_migrated_operational_code_uses_no_legacy_inventory_sources() -> None:
    operational_files = [
        PACKAGE_ROOT / "backend" / "application" / "services" / "inventory_application_service.py",
        PACKAGE_ROOT / "backend" / "infrastructure" / "db" / "repositories" / "inventory_repository.py",
        PACKAGE_ROOT / "backend" / "application" / "services" / "waste_application_service.py",
        PACKAGE_ROOT / "backend" / "infrastructure" / "db" / "repositories" / "waste_repository.py",
        PACKAGE_ROOT / "core" / "services" / "purchase_service.py",
        PACKAGE_ROOT / "application" / "purchases" / "receive_po_adapter.py",
    ]
    forbidden = [
        "productos.existencia",
        "UPDATE productos SET existencia",
        "inventario_actual",
        "branch_inventory",
        "movimientos_inventario",
        ".add_stock(",
        ".deduct_stock(",
    ]
    violations = {
        str(path.relative_to(PACKAGE_ROOT)): [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for path in operational_files
    }
    assert {path: tokens for path, tokens in violations.items() if tokens} == {}
