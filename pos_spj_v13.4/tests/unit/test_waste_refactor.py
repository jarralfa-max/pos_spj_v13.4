from __future__ import annotations

import sqlite3

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
        date="2026-06-05",
    ))

    products = repository.search_products("arra")
    rows = repository.list_waste_records(branch_id="1", period="Todo")
    summary = repository.get_daily_summary(branch_id="1")

    assert products[0].label == "Arrachera"
    assert rows[0].values["product_name"] == "Arrachera"
    assert rows[0].values["loss_value"] == 156.88
    assert summary.value["records"] == 1
