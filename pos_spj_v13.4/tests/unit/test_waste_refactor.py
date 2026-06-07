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


def test_register_waste_above_stock_clamps_inventory_to_zero_for_audit() -> None:
    conn = _db()
    repository = WasteRepository(conn)
    use_case = RegisterWasteUseCase(app_service=WasteApplicationService(repository=repository))

    result = use_case.execute(RegisterWasteCommand(
        operation_id="overstock-waste-1",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=12.0,
        reason="Merma mayor al stock",
        date="2026-06-05",
    ))

    assert result.success is True
    assert conn.execute("SELECT existencia FROM productos WHERE id = 1").fetchone()[0] == 0
    waste_row = conn.execute(
        "SELECT cantidad, valor_perdida FROM mermas WHERE operation_id = 'overstock-waste-1'"
    ).fetchone()
    assert waste_row == (12.0, 1506.0)


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
    repository = WasteRepository(conn)
    service = WasteApplicationService(
        repository=repository,
        event_bus=bus,
        finance_handler=ExplodingFinanceHandler(),
    )

    result = service.register(RegisterWasteCommand(
        operation_id="finance-side-effect-fails",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=1.0,
        reason="Merma con finanzas caídas",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.data["side_effect_errors"] == ("WASTE_FINANCE_RECORD_FAILED",)
    assert conn.execute("SELECT COUNT(*) FROM mermas WHERE operation_id = 'finance-side-effect-fails'").fetchone()[0] == 1
    assert conn.execute("SELECT existencia FROM productos WHERE id = 1").fetchone()[0] == 9.0
    assert len(events) == 1
    assert "finance side-effect failed" in caplog.text


def test_register_waste_event_publish_failure_is_logged_non_fatal_after_persistence(caplog) -> None:
    conn = _db()
    finance = FinanceSpy()
    repository = WasteRepository(conn)
    service = WasteApplicationService(
        repository=repository,
        event_bus=ExplodingEventBus(),
        finance_handler=finance,
    )

    result = service.register(RegisterWasteCommand(
        operation_id="event-side-effect-fails",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=1.0,
        reason="Merma con eventos caídos",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.data["side_effect_errors"] == ("WASTE_EVENT_PUBLISH_FAILED",)
    assert result.events == ()
    assert conn.execute("SELECT COUNT(*) FROM mermas WHERE operation_id = 'event-side-effect-fails'").fetchone()[0] == 1
    assert conn.execute("SELECT existencia FROM productos WHERE id = 1").fetchone()[0] == 9.0
    assert len(finance.entries) == 1
    assert "event publish failed" in caplog.text


class FailingDecreaseWasteRepository(WasteRepository):
    def decrease_inventory_for_waste(
        self,
        product_id,
        quantity,
        *,
        branch_id=None,
        unit_cost=0.0,
        operation_id=None,
        reason="",
        user_name="",
    ) -> None:
        raise RuntimeError("inventory update failed")


def test_register_waste_rolls_back_when_inventory_decrease_fails(caplog) -> None:
    conn = _db()
    finance = FinanceSpy()
    bus = InMemoryEventBus()
    events = []
    bus.subscribe(EventName.WASTE_REGISTERED, events.append)
    repository = FailingDecreaseWasteRepository(conn)
    service = WasteApplicationService(repository=repository, event_bus=bus, finance_handler=finance)

    result = service.register(RegisterWasteCommand(
        operation_id="inventory-critical-fails",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=1.0,
        reason="Falla crítica de inventario",
        date="2026-06-05",
    ))

    assert result.success is False
    assert result.message == "WASTE_REGISTER_FAILED"
    assert conn.execute("SELECT COUNT(*) FROM mermas WHERE operation_id = 'inventory-critical-fails'").fetchone()[0] == 0
    assert conn.execute("SELECT existencia FROM productos WHERE id = 1").fetchone()[0] == 10.0
    assert finance.entries == []
    assert events == []
    assert "critical persistence failed; rolled back" in caplog.text


def test_register_waste_uses_real_cost_fallback_records_inventory_movement_and_financial_log() -> None:
    from core.services.finance.general_ledger_service import GeneralLedgerService

    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
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
    conn.execute("""
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            tipo TEXT,
            tipo_movimiento TEXT,
            cantidad REAL,
            existencia_anterior REAL,
            existencia_nueva REAL,
            costo_unitario REAL,
            costo_total REAL,
            descripcion TEXT,
            referencia TEXT,
            referencia_tipo TEXT,
            operation_id TEXT,
            usuario TEXT,
            sucursal_id TEXT,
            fecha TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn.execute(
        """
        INSERT INTO productos(id, nombre, precio_compra, costo, precio_costo, costo_unitario, unidad, existencia, activo)
        VALUES (1, 'Producto costo real', '', 50, 40, 30, 'kg', 10, 1)
        """
    )
    conn.commit()

    repository = WasteRepository(conn)
    service = WasteApplicationService(
        repository=repository,
        finance_handler=GeneralLedgerService(conn),
    )

    result = service.register(RegisterWasteCommand(
        operation_id="cost-fallback-op",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=2.0,
        reason="Merma por daño",
        date="2026-06-05",
    ))

    assert result.success is True
    assert result.data["unit_cost"] == 50.0
    assert result.data["loss_value"] == 100.0
    assert conn.execute("SELECT existencia FROM productos WHERE id = 1").fetchone()[0] == 8.0
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
        SELECT tipo, tipo_movimiento, cantidad, existencia_anterior, existencia_nueva,
               costo_unitario, costo_total, operation_id
        FROM movimientos_inventario
        WHERE operation_id = 'cost-fallback-op'
        """
    ).fetchone()
    assert movement_row == ("MERMA", "waste", 2.0, 10.0, 8.0, 50.0, 100.0, "cost-fallback-op")
    finance_row = conn.execute(
        """
        SELECT evento, modulo, monto, cuenta_debe, cuenta_haber
        FROM financial_event_log
        WHERE evento = 'WASTE_REGISTERED'
        """
    ).fetchone()
    assert finance_row == ("WASTE_REGISTERED", "waste", 100.0, "mermas_y_deterioro", "inventario_almacen")


def test_branch_inventory_decrease_consumes_only_needed_rows_without_discounting_every_row() -> None:
    conn = _db()
    conn.execute("UPDATE productos SET existencia = 10 WHERE id = 1")
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
    conn.execute(
        "INSERT INTO branch_inventory(product_id, branch_id, quantity, batch_id) VALUES (1, 1, 7, NULL)"
    )
    conn.execute(
        "INSERT INTO branch_inventory(product_id, branch_id, quantity, batch_id) VALUES (1, 1, 3, 99)"
    )
    conn.commit()

    repository = WasteRepository(conn)
    result = WasteApplicationService(repository=repository).register(RegisterWasteCommand(
        operation_id="branch-row-safe-op",
        branch_id="1",
        user_name="ana",
        product_id=1,
        quantity=2.0,
        reason="Merma parcial",
        date="2026-06-05",
    ))

    assert result.success is True
    rows = conn.execute(
        "SELECT batch_id, quantity FROM branch_inventory WHERE product_id = 1 AND branch_id = 1 ORDER BY batch_id IS NOT NULL, batch_id"
    ).fetchall()
    assert rows[0] == (None, 5.0)
    assert rows[1] == (99, 3.0)
    assert sum(row[1] for row in rows) == 8.0
    assert conn.execute("SELECT existencia FROM productos WHERE id = 1").fetchone()[0] == 8.0


def _index_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_waste_schema_integrity_migration_adds_required_columns_indexes_and_unique_operation_id() -> None:
    import importlib

    migration = importlib.import_module("migrations.standalone.097_waste_schema_integrity")
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT)")
    conn.execute("""
        CREATE TABLE mermas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER NOT NULL,
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
        INSERT INTO mermas(producto_id, sucursal_id, cantidad, motivo, usuario, operation_id)
        VALUES (1, 1, 1, 'Rotura', 'ana', 'same-op')
    """)
    try:
        conn.execute("""
            INSERT INTO mermas(producto_id, sucursal_id, cantidad, motivo, usuario, operation_id)
            VALUES (1, 1, 1, 'Rotura', 'ana', 'same-op')
        """)
    except sqlite3.IntegrityError:
        duplicate_rejected = True
    else:
        duplicate_rejected = False
    assert duplicate_rejected is True


def test_waste_schema_integrity_migration_skips_unique_index_when_existing_duplicates(caplog) -> None:
    import importlib

    migration = importlib.import_module("migrations.standalone.097_waste_schema_integrity")
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE mermas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER NOT NULL,
            cantidad REAL NOT NULL,
            unidad TEXT,
            motivo TEXT,
            usuario TEXT,
            operation_id TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        INSERT INTO mermas(producto_id, sucursal_id, cantidad, motivo, usuario, operation_id)
        VALUES (1, 1, 1, 'Rotura', 'ana', 'dup-op')
    """)
    conn.execute("""
        INSERT INTO mermas(producto_id, sucursal_id, cantidad, motivo, usuario, operation_id)
        VALUES (1, 1, 2, 'Rotura', 'ana', 'dup-op')
    """)

    migration.run(conn)

    indexes = _index_names(conn, "mermas")
    assert "idx_mermas_operation_id" in indexes
    assert "ux_mermas_operation_id" not in indexes
    assert "duplicate mermas.operation_id values found" in caplog.text
