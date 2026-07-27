from __future__ import annotations

import importlib
import sqlite3
from datetime import date

from backend.application.commands.waste_commands import RegisterWasteCommand
from backend.application.services.inventory_application_service import InventoryApplicationService
from backend.application.services.waste_application_service import WasteApplicationService
from backend.application.use_cases.register_waste_use_case import RegisterWasteUseCase
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository
from backend.infrastructure.db.repositories.waste_repository import WasteRepository
from backend.shared.events.event_bus import InMemoryEventBus
from backend.shared.events.event_names import EventName

# Canonical UUIDs for all test entities
PRODUCT_UUID = "01900000-0000-7000-8000-000000000001"
BRANCH_1_UUID = "01900000-0000-7000-8000-000000000011"
BRANCH_2_UUID = "01900000-0000-7000-8000-000000000012"


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
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio_compra REAL,
            costo REAL,
            precio_costo REAL,
            costo_unitario REAL,
            unidad TEXT,
            existencia REAL,
            activo INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE mermas (
            id TEXT PRIMARY KEY,
            producto_id TEXT NOT NULL,
            sucursal_id TEXT NOT NULL,
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
    importlib.import_module("migrations.standalone.098_canonical_inventory").run(conn)
    conn.execute(
        """
        INSERT INTO productos(id, nombre, precio_compra, costo, precio_costo, costo_unitario, unidad, existencia, activo)
        VALUES (?, 'Arrachera', 125.5, NULL, NULL, NULL, 'kg', 10, 1)
        """,
        (PRODUCT_UUID,),
    )
    conn.execute(
        "INSERT INTO inventory_stock(product_id, branch_id, quantity, unit) VALUES (?, ?, 10, 'kg')",
        (PRODUCT_UUID, BRANCH_1_UUID),
    )
    conn.execute(
        "INSERT INTO inventory_stock(product_id, branch_id, quantity, unit) VALUES (?, ?, 10, 'kg')",
        (PRODUCT_UUID, BRANCH_2_UUID),
    )
    conn.commit()
    return conn


def _inventory_service(conn: sqlite3.Connection, bus=None) -> InventoryApplicationService:
    return InventoryApplicationService(repository=InventoryRepository(conn), event_bus=bus or InMemoryEventBus())


def _waste_service(conn: sqlite3.Connection, *, bus=None, inventory_bus=None, finance_handler=None) -> WasteApplicationService:
    return WasteApplicationService(
        repository=WasteRepository(conn),
        inventory_service=_inventory_service(conn, inventory_bus if inventory_bus is not None else bus),
        event_bus=bus,
        finance_handler=finance_handler,
    )


def test_register_waste_use_case_persists_decreases_canonical_inventory_finance_and_events() -> None:
    conn = _db()
    finance = FinanceSpy()
    bus = InMemoryEventBus()
    waste_events = []
    movement_events = []
    stock_events = []
    bus.subscribe(EventName.WASTE_REGISTERED, waste_events.append)
    bus.subscribe(EventName.INVENTORY_MOVEMENT_RECORDED, movement_events.append)
    bus.subscribe(EventName.INVENTORY_STOCK_UPDATED, stock_events.append)

    use_case = RegisterWasteUseCase(app_service=_waste_service(conn, bus=bus, finance_handler=finance))

    result = use_case.execute(RegisterWasteCommand(
        operation_id="op-waste-1",
        branch_id=BRANCH_2_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=2.5,
        reason="Caducidad / vencimiento",
        notes="empaque abierto",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.operation_id == "op-waste-1"
    assert result.data["loss_value"] == 313.75
    assert result.data["inventory_source"] == "inventory_stock"
    assert result.data["stock_before"] == 10.0
    assert result.data["stock_after"] == 7.5
    assert conn.execute("SELECT existencia FROM productos WHERE id=?", (PRODUCT_UUID,)).fetchone()[0] == 10.0
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_2_UUID),
    ).fetchone()[0] == 7.5
    movement_row = conn.execute(
        """
        SELECT operation_id, movement_type, quantity, stock_before, stock_after, source_module, reference_type
        FROM inventory_movements
        WHERE operation_id = 'op-waste-1'
        """
    ).fetchone()
    assert movement_row == ("op-waste-1", "DECREASE", 2.5, 10.0, 7.5, "waste", "WASTE")
    waste_row = conn.execute("SELECT producto_id, cantidad, valor_perdida, operation_id FROM mermas").fetchone()
    assert waste_row == (PRODUCT_UUID, 2.5, 313.75, "op-waste-1")
    assert len(finance.entries) == 1
    assert finance.entries[0]["monto"] == 313.75
    assert len(waste_events) == 1
    assert len(movement_events) == 1
    assert len(stock_events) == 1
    assert waste_events[0].event_name == EventName.WASTE_REGISTERED
    assert waste_events[0].payload["stock_after"] == 7.5


def test_register_waste_use_case_rejects_duplicate_operation_id() -> None:
    conn = _db()
    use_case = RegisterWasteUseCase(app_service=_waste_service(conn))
    command = RegisterWasteCommand(
        operation_id="dup-op",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
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
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 9.0


def test_waste_query_service_reads_canonical_stock_products_history_and_summary() -> None:
    conn = _db()
    repository = WasteRepository(conn)
    service = _waste_service(conn)
    service.register(RegisterWasteCommand(
        operation_id="query-op",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=1.25,
        reason="Caducidad / vencimiento",
        date=date.today().isoformat(),
    ))

    products = repository.search_products("arra", branch_id=BRANCH_1_UUID)
    rows = repository.list_waste_records(branch_id=BRANCH_1_UUID, period="Todo")
    summary = repository.get_daily_summary(branch_id=BRANCH_1_UUID)

    assert products[0].label == "Arrachera"
    assert products[0].metadata["unit"] == "kg"
    assert rows[0].values["product_name"] == "Arrachera"
    assert rows[0].values["loss_value"] == 156.88
    assert summary.value["records"] == 1


def test_merma_of_one_over_stock_ten_leaves_canonical_stock_nine() -> None:
    conn = _db()

    result = _waste_service(conn).register(RegisterWasteCommand(
        operation_id="waste-one-from-ten",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=1,
        reason="Merma exacta",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.data["stock_before"] == 10.0
    assert result.data["stock_after"] == 9.0
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 9.0


def test_register_waste_blocks_negative_canonical_stock_and_rolls_back_waste() -> None:
    conn = _db()

    result = _waste_service(conn).register(RegisterWasteCommand(
        operation_id="negative-stock-op",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=11.0,
        reason="Cantidad inválida",
        date="2026-06-05",
    ))

    assert result.success is False
    assert result.message == "WASTE_REGISTER_FAILED"
    assert conn.execute("SELECT COUNT(*) FROM mermas WHERE operation_id = 'negative-stock-op'").fetchone()[0] == 0
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 10.0
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements WHERE operation_id = 'negative-stock-op'").fetchone()[0] == 0


def test_waste_is_multi_branch_and_does_not_affect_other_branch() -> None:
    conn = _db()
    conn.execute(
        "UPDATE inventory_stock SET quantity = 5 WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_2_UUID),
    )
    conn.commit()

    result = _waste_service(conn).register(RegisterWasteCommand(
        operation_id="branch-one-only",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=1,
        reason="Merma sucursal 1",
        date="2026-06-05",
    ))

    assert result.success is True
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 9.0
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_2_UUID),
    ).fetchone()[0] == 5.0


def test_waste_does_not_touch_legacy_inventory_tables_or_product_existence() -> None:
    conn = _db()
    conn.execute("""
        CREATE TABLE branch_inventory (
            id TEXT PRIMARY KEY,
            branch_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE inventario_actual (
            id TEXT PRIMARY KEY,
            producto_id TEXT NOT NULL,
            sucursal_id TEXT NOT NULL,
            cantidad REAL NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE movimientos_inventario (
            id TEXT PRIMARY KEY,
            producto_id TEXT,
            cantidad REAL,
            operation_id TEXT
        )
    """)
    conn.execute(
        "INSERT INTO branch_inventory(id, product_id, branch_id, quantity) VALUES (?, ?, ?, 99)",
        ("bi-1", PRODUCT_UUID, BRANCH_1_UUID),
    )
    conn.execute(
        "INSERT INTO inventario_actual(id, producto_id, sucursal_id, cantidad) VALUES (?, ?, ?, 88)",
        ("ia-1", PRODUCT_UUID, BRANCH_1_UUID),
    )
    conn.commit()

    result = _waste_service(conn).register(RegisterWasteCommand(
        operation_id="legacy-untouched-op",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=1,
        reason="Merma canónica",
        date="2026-06-05",
    ))

    assert result.success is True
    assert conn.execute("SELECT existencia FROM productos WHERE id = ?", (PRODUCT_UUID,)).fetchone()[0] == 10.0
    assert conn.execute(
        "SELECT quantity FROM branch_inventory WHERE product_id = ? AND branch_id = ?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 99.0
    assert conn.execute(
        "SELECT cantidad FROM inventario_actual WHERE producto_id = ? AND sucursal_id = ?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 88.0
    assert conn.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0] == 0


class ExplodingFinanceHandler:
    def record_loss(self, **_kwargs):
        raise RuntimeError("finance unavailable")


class ExplodingEventBus:
    def publish(self, _event):
        raise RuntimeError("event bus unavailable")


def test_register_waste_finance_failure_is_logged_non_fatal_and_event_still_publishes(caplog) -> None:
    conn = _db()
    bus = InMemoryEventBus()
    events = []
    bus.subscribe(EventName.WASTE_REGISTERED, events.append)

    result = _waste_service(conn, bus=bus, finance_handler=ExplodingFinanceHandler()).register(RegisterWasteCommand(
        operation_id="finance-side-effect-fails",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=1.0,
        reason="Merma con finanzas caídas",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.data["side_effect_errors"] == ("WASTE_FINANCE_RECORD_FAILED",)
    assert conn.execute("SELECT COUNT(*) FROM mermas WHERE operation_id = 'finance-side-effect-fails'").fetchone()[0] == 1
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 9.0
    assert len(events) == 1
    assert "finance side-effect failed" in caplog.text


def test_register_waste_event_publish_failure_is_logged_non_fatal_after_persistence(caplog) -> None:
    conn = _db()
    finance = FinanceSpy()

    result = _waste_service(
        conn,
        bus=ExplodingEventBus(),
        inventory_bus=InMemoryEventBus(),
        finance_handler=finance,
    ).register(RegisterWasteCommand(
        operation_id="event-side-effect-fails",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=1.0,
        reason="Merma con eventos caídos",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.data["side_effect_errors"] == ("WASTE_EVENT_PUBLISH_FAILED",)
    assert conn.execute("SELECT COUNT(*) FROM mermas WHERE operation_id = 'event-side-effect-fails'").fetchone()[0] == 1
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 9.0
    assert len(finance.entries) == 1
    assert "event publish failed" in caplog.text


def test_register_waste_uses_real_cost_fallback_and_financial_log() -> None:
    from core.services.finance.general_ledger_service import GeneralLedgerService

    conn = _db()
    conn.execute(
        "UPDATE productos SET precio_compra = '', costo = 50, precio_costo = 40, costo_unitario = 30 WHERE id = ?",
        (PRODUCT_UUID,),
    )
    conn.execute("""
        CREATE TABLE financial_event_log (
            id TEXT PRIMARY KEY,
            evento TEXT,
            modulo TEXT,
            referencia_id TEXT,
            monto REAL,
            cuenta_debe TEXT,
            cuenta_haber TEXT,
            usuario_id TEXT,
            sucursal_id TEXT,
            metadata TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    result = _waste_service(conn, finance_handler=GeneralLedgerService(conn)).register(RegisterWasteCommand(
        operation_id="cost-fallback-op",
        branch_id=BRANCH_1_UUID,
        user_name="ana",
        product_id=PRODUCT_UUID,
        quantity=2.0,
        reason="Merma por daño",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.data["unit_cost"] == 50.0
    assert result.data["loss_value"] == 100.0
    assert conn.execute(
        "SELECT quantity FROM inventory_stock WHERE product_id=? AND branch_id=?",
        (PRODUCT_UUID, BRANCH_1_UUID),
    ).fetchone()[0] == 8.0
    assert conn.execute("SELECT existencia FROM productos WHERE id = ?", (PRODUCT_UUID,)).fetchone()[0] == 10.0
    waste_row = conn.execute(
        """
        SELECT cantidad, costo_unitario, valor_perdida
        FROM mermas
        WHERE operation_id = 'cost-fallback-op'
        """
    ).fetchone()
    assert waste_row == (2.0, 50.0, 100.0)
    movement_row = conn.execute(
        """
        SELECT movement_type, quantity, stock_before, stock_after, source_module, reference_type, operation_id
        FROM inventory_movements
        WHERE operation_id = 'cost-fallback-op'
        """
    ).fetchone()
    assert movement_row == ("DECREASE", 2.0, 10.0, 8.0, "waste", "WASTE", "cost-fallback-op")
    finance_row = conn.execute(
        """
        SELECT evento, modulo, monto, cuenta_debe, cuenta_haber
        FROM financial_event_log
        WHERE evento = 'WASTE_REGISTERED'
        """
    ).fetchone()
    assert finance_row == ("WASTE_REGISTERED", "waste", 100.0, "mermas_y_deterioro", "inventario_almacen")


def _index_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_waste_schema_integrity_migration_adds_required_columns_indexes_and_unique_operation_id() -> None:
    migration = importlib.import_module("migrations.standalone.097_waste_schema_integrity")
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE productos (id TEXT PRIMARY KEY, nombre TEXT)")
    conn.execute("""
        CREATE TABLE mermas (
            id TEXT PRIMARY KEY,
            producto_id TEXT NOT NULL,
            sucursal_id TEXT NOT NULL,
            cantidad REAL NOT NULL,
            unidad TEXT,
            motivo TEXT,
            usuario TEXT,
            operation_id TEXT,
            created_at TEXT
        )
    """)

    migration.run(conn)
    migration.run(conn)

    assert {"costo_unitario", "valor_perdida", "notas", "fecha"}.issubset(_column_names(conn, "mermas"))
    indexes = _index_names(conn, "mermas")
    assert "idx_mermas_producto_id" in indexes
    assert "idx_mermas_sucursal_id" in indexes
    assert "idx_mermas_fecha" in indexes
    assert "idx_mermas_producto_sucursal_fecha" in indexes
    assert "ux_mermas_operation_id" in indexes
    assert "idx_productos_nombre" in _index_names(conn, "productos")

    conn.execute("""
        INSERT INTO mermas(id, producto_id, sucursal_id, cantidad, motivo, usuario, operation_id)
        VALUES ('m1', 'p1', 's1', 1, 'Rotura', 'ana', 'same-op')
    """)
    try:
        conn.execute("""
            INSERT INTO mermas(id, producto_id, sucursal_id, cantidad, motivo, usuario, operation_id)
            VALUES ('m2', 'p1', 's1', 1, 'Rotura', 'ana', 'same-op')
        """)
    except sqlite3.IntegrityError:
        duplicate_rejected = True
    else:
        duplicate_rejected = False
    assert duplicate_rejected is True


def test_waste_schema_integrity_migration_skips_unique_index_when_existing_duplicates(caplog) -> None:
    migration = importlib.import_module("migrations.standalone.097_waste_schema_integrity")
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE mermas (
            id TEXT PRIMARY KEY,
            producto_id TEXT NOT NULL,
            sucursal_id TEXT NOT NULL,
            cantidad REAL NOT NULL,
            unidad TEXT,
            motivo TEXT,
            usuario TEXT,
            operation_id TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        INSERT INTO mermas(id, producto_id, sucursal_id, cantidad, motivo, usuario, operation_id)
        VALUES ('m1', 'p1', 's1', 1, 'Rotura', 'ana', 'dup-op')
    """)
    conn.execute("""
        INSERT INTO mermas(id, producto_id, sucursal_id, cantidad, motivo, usuario, operation_id)
        VALUES ('m2', 'p1', 's1', 2, 'Rotura', 'ana', 'dup-op')
    """)

    migration.run(conn)

    indexes = _index_names(conn, "mermas")
    assert "idx_mermas_operation_id" in indexes
    assert "ux_mermas_operation_id" not in indexes
    assert "duplicate mermas.operation_id values found" in caplog.text
