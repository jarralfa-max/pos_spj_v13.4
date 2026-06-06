from __future__ import annotations

import sqlite3
from datetime import date

from backend.application.commands.waste_commands import RegisterWasteCommand
from backend.application.services.waste_application_service import WasteApplicationService
from backend.application.use_cases.register_waste_use_case import RegisterWasteUseCase
from backend.infrastructure.db.repositories.waste_repository import WasteRepository
from backend.shared.events.event_bus import InMemoryEventBus
from backend.shared.events.event_names import EventName


class FinanceSpy:
    def __init__(self) -> None:
        self.entries = []

    def registrar_asiento(self, **kwargs):
        self.entries.append(kwargs)
        return {"ok": True}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio_compra REAL,
            unidad TEXT,
            existencia REAL,
            activo INTEGER
        )
    """)
    conn.execute("""
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
    """)
    conn.execute(
        "INSERT INTO productos(id, nombre, precio_compra, unidad, existencia, activo) VALUES (1, 'Arrachera', 125.5, 'kg', 10, 1)"
    )
    conn.commit()
    return conn


def test_register_waste_use_case_persists_decreases_inventory_finance_and_event() -> None:
    conn = _db()
    finance = FinanceSpy()
    bus = InMemoryEventBus()
    events = []
    bus.subscribe(EventName.WASTE_REGISTERED, events.append)

    repository = WasteRepository(conn)
    app_service = WasteApplicationService(repository=repository, event_bus=bus, finance_handler=finance)
    use_case = RegisterWasteUseCase(app_service=app_service)

    result = use_case.execute(RegisterWasteCommand(
        operation_id="op-waste-1",
        branch_id="2",
        user_name="ana",
        product_id=1,
        quantity=2.5,
        reason="Caducidad / vencimiento",
        notes="empaque abierto",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.operation_id == "op-waste-1"
    assert result.data["loss_value"] == 313.75
    assert conn.execute("SELECT existencia FROM productos WHERE id=1").fetchone()[0] == 7.5
    waste_row = conn.execute("SELECT producto_id, cantidad, valor_perdida, operation_id FROM mermas").fetchone()
    assert waste_row == (1, 2.5, 313.75, "op-waste-1")
    assert len(finance.entries) == 1
    assert finance.entries[0]["monto"] == 313.75
    assert len(events) == 1
    assert events[0].event_name == EventName.WASTE_REGISTERED
    assert events[0].operation_id == "op-waste-1"
    assert events[0].payload["product_id"] == 1


def test_register_waste_use_case_rejects_duplicate_operation_id() -> None:
    conn = _db()
    repository = WasteRepository(conn)
    use_case = RegisterWasteUseCase(app_service=WasteApplicationService(repository=repository))
    command = RegisterWasteCommand(
        operation_id="dup-op",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=1,
        reason="Daño en manipulación",
        date="2026-06-05",
    )

    first = use_case.execute(command)
    second = use_case.execute(command)

    assert first.success is True
    assert second.success is False
    assert second.message == "WASTE_OPERATION_ALREADY_REGISTERED"
    assert conn.execute("SELECT COUNT(*) FROM mermas").fetchone()[0] == 1


def test_waste_query_service_reads_products_history_and_summary() -> None:
    conn = _db()
    repository = WasteRepository(conn)
    service = WasteApplicationService(repository=repository)
    service.register(RegisterWasteCommand(
        operation_id="query-op",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=1.25,
        reason="Caducidad / vencimiento",
        date=date.today().isoformat(),
    ))

    products = repository.search_products("arra")
    rows = repository.list_waste_records(branch_id="1", period="Todo")
    summary = repository.get_daily_summary(branch_id="1")

    assert products[0].label == "Arrachera"
    assert rows[0].values["product_name"] == "Arrachera"
    assert rows[0].values["loss_value"] == 156.88
    assert summary.value["records"] == 1


def test_waste_repository_uses_branch_inventory_for_waste_stock_and_decrease() -> None:
    conn = _db()
    conn.execute("UPDATE productos SET existencia = 14 WHERE id = 1")
    conn.execute("""
        CREATE TABLE branch_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            batch_id INTEGER,
            quantity REAL NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER NOT NULL,
            cantidad REAL NOT NULL DEFAULT 0,
            costo_promedio REAL DEFAULT 0,
            ultima_actualizacion TEXT DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id)
        )
    """)
    conn.execute(
        "INSERT INTO branch_inventory(product_id, branch_id, quantity, batch_id) VALUES (1, 1, 10, NULL)"
    )
    conn.execute(
        "INSERT INTO branch_inventory(product_id, branch_id, quantity, batch_id) VALUES (1, 2, 4, NULL)"
    )
    conn.execute(
        "INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad) VALUES (1, 1, 10)"
    )
    conn.execute(
        "INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad) VALUES (1, 2, 4)"
    )
    conn.commit()

    repository = WasteRepository(conn)
    use_case = RegisterWasteUseCase(app_service=WasteApplicationService(repository=repository))

    product = repository.get_product_for_waste(1, branch_id="2")
    search_result = repository.search_products("arra", branch_id="2")[0]
    result = use_case.execute(RegisterWasteCommand(
        operation_id="branch-waste-1",
        branch_id="2",
        user_name="ana",
        product_id=1,
        quantity=1.5,
        reason="Merma de sucursal",
        date="2026-06-05",
    ))

    assert product["stock"] == 4.0
    assert search_result.metadata["stock"] == 4.0
    assert result.success is True
    assert conn.execute(
        "SELECT quantity FROM branch_inventory WHERE product_id = 1 AND branch_id = 2 AND batch_id IS NULL"
    ).fetchone()[0] == 2.5
    assert conn.execute(
        "SELECT quantity FROM branch_inventory WHERE product_id = 1 AND branch_id = 1 AND batch_id IS NULL"
    ).fetchone()[0] == 10.0
    assert conn.execute(
        "SELECT cantidad FROM inventario_actual WHERE producto_id = 1 AND sucursal_id = 2"
    ).fetchone()[0] == 2.5
    assert conn.execute("SELECT existencia FROM productos WHERE id = 1").fetchone()[0] == 12.5
    branch_row = conn.execute("SELECT sucursal_id FROM mermas WHERE operation_id = 'branch-waste-1'").fetchone()
    assert str(branch_row[0]) == "2"
