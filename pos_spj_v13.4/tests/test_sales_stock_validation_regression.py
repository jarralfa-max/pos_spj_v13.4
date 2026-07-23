import sqlite3
from unittest.mock import MagicMock

import pytest

from core.events.domain_events import SALE_ITEMS_PROCESS
from core.events.event_bus import get_bus
from core.services.sales_fulfillment_service import SaleFulfillmentService
from core.services.sales_service import SalesService


class _SqlSalesRepo:
    def __init__(self, db):
        self.db = db

    def create_sale(self, **kwargs):
        cur = self.db.execute(
            """
            INSERT INTO ventas(folio, sucursal_id, usuario, cliente_id, subtotal, descuento, total, forma_pago)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                "F-STOCK-1",
                kwargs.get("branch_id"),
                kwargs.get("user"),
                kwargs.get("client_id"),
                kwargs.get("subtotal"),
                kwargs.get("discount"),
                kwargs.get("total"),
                kwargs.get("payment_method"),
            ),
        )
        return int(cur.lastrowid), "F-STOCK-1"

    def save_sale_item(self, sale_id, product_id, qty, unit_price, subtotal):
        self.db.execute(
            "INSERT INTO detalles_venta(venta_id, producto_id, cantidad, precio_unitario, subtotal) VALUES(?,?,?,?,?)",
            (sale_id, product_id, qty, unit_price, subtotal),
        )


def _db_with_basic_sales_schema(stock=10.0):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, existencia REAL, unidad TEXT)")
    db.execute("INSERT INTO productos(id,nombre,existencia,unidad) VALUES(1,'Pollo',?, 'kg')", (stock,))
    db.execute(
        """
        CREATE TABLE ventas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            sucursal_id INTEGER,
            usuario TEXT,
            cliente_id INTEGER,
            subtotal REAL,
            descuento REAL,
            total REAL,
            forma_pago TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE detalles_venta(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            producto_id INTEGER,
            cantidad REAL,
            precio_unitario REAL,
            subtotal REAL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE movimientos_caja(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            monto REAL,
            descripcion TEXT
        )
        """
    )
    return db


def _build_sales_service(db):
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: "<html>{{folio}}</html>" if key == "ticket_template_html" else default
    ticket_engine = MagicMock()
    ticket_engine.generar_ticket.return_value = "<html>F-STOCK-1</html>"
    loyalty = MagicMock()
    loyalty.compute_redemption_discount.return_value = 0.0
    loyalty.process_raffles_for_sale.return_value = []
    customer = MagicMock()
    customer.get_customer.return_value = {"id": 1}
    customer.validate_credit.return_value = (True, "")
    svc = SalesService(
        db_conn=db,
        sales_repo=_SqlSalesRepo(db),
        recipe_repo=MagicMock(),
        inventory_service=MagicMock(),
        finance_service=MagicMock(),
        loyalty_service=loyalty,
        promotion_engine=None,
        sync_service=None,
        ticket_template_engine=ticket_engine,
        whatsapp_service=MagicMock(),
        config_service=config,
        feature_flag_service=MagicMock(),
        growth_engine=MagicMock(),
        notification_service=MagicMock(),
        customer_service=customer,
    )
    svc._lote_svc = None
    svc._loyalty_policy = MagicMock(return_value=None)
    svc._resolve_sale_items = MagicMock(
        return_value=[{"product_id": 1, "qty": 1.0, "cantidad": 1.0, "unit_price": 10.0, "es_compuesto": 0}]
    )
    return svc


class _BusSnapshot:
    def __init__(self):
        self.bus = get_bus()
        self.handlers = {k: list(v) for k, v in getattr(self.bus, "_handlers", {}).items()}

    def restore(self):
        self.bus.clear_handlers()
        for event, handlers in self.handlers.items():
            for priority, label, handler in handlers:
                self.bus.subscribe(event, handler, priority=priority, label=label)


def test_prevalidate_stock_fails_before_event_when_insufficient():
    db = _db_with_basic_sales_schema(stock=0.25)
    svc = _build_sales_service(db)
    snapshot = _BusSnapshot()
    published = []
    try:
        get_bus().clear_handlers(SALE_ITEMS_PROCESS)
        get_bus().subscribe(SALE_ITEMS_PROCESS, lambda payload: published.append(payload), priority=100, label="sale_inventory_test")
        get_bus().subscribe(SALE_ITEMS_PROCESS, lambda payload: None, priority=90, label="sale_finance_test")

        with pytest.raises(RuntimeError, match="STOCK_INSUFICIENTE"):
            svc.execute_sale(
                branch_id=1,
                user="cajero",
                items=[{"product_id": 1, "qty": 1, "unit_price": 10}],
                payment_method="Efectivo",
                amount_paid=10,
                client_id=1,
            )

        assert published == []
        assert db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0
    finally:
        snapshot.restore()


def test_prevalidate_stock_uses_existing_schema_only():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    # Minimal old schema: no tipo_producto/es_compuesto/es_subproducto columns.
    db.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, existencia REAL, unidad TEXT)")
    db.execute("INSERT INTO productos(id,nombre,existencia,unidad) VALUES(1,'Pollo',5,'kg')")

    lines = SaleFulfillmentService(db).resolve_item(1, 2, 1)

    assert len(lines) == 1
    assert lines[0].product_id == 1
    assert lines[0].qty == 2


def test_prevalidate_stock_handles_recipe_schema_without_cantidad_column():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, existencia REAL, unidad TEXT, tipo_producto TEXT)"
    )
    db.execute("INSERT INTO productos(id,nombre,existencia,unidad,tipo_producto) VALUES(1,'Milanesa',0,'kg','procesable')")
    db.execute("INSERT INTO productos(id,nombre,existencia,unidad,tipo_producto) VALUES(2,'Pechuga',10,'kg','simple')")
    db.execute("CREATE TABLE product_recipes(id INTEGER PRIMARY KEY, base_product_id INTEGER, is_active INTEGER)")
    db.execute("CREATE TABLE product_recipe_components(recipe_id INTEGER, component_product_id INTEGER, quantity REAL)")
    db.execute("INSERT INTO product_recipes(id,base_product_id,is_active) VALUES(7,1,1)")
    db.execute("INSERT INTO product_recipe_components(recipe_id,component_product_id,quantity) VALUES(7,2,2.0)")

    lines = SaleFulfillmentService(db).resolve_item(1, 2, 1)

    assert len(lines) == 1
    assert lines[0].product_id == 2
    assert lines[0].qty == 4.0
    assert lines[0].mode == "VIRTUAL_FROM_COMPONENTS"




def test_sale_rollback_keeps_cash_and_inventory_intact():
    db = _db_with_basic_sales_schema(stock=5.0)
    svc = _build_sales_service(db)
    snapshot = _BusSnapshot()
    try:
        get_bus().clear_handlers(SALE_ITEMS_PROCESS)

        def _inventory_race(payload):
            raise RuntimeError("Inventario cambió antes del commit")

        def _finance_should_not_run(payload):
            db.execute(
                "INSERT INTO movimientos_caja(venta_id,monto,descripcion) VALUES(?,?,?)",
                (payload.get("sale_id"), payload.get("total"), "NO_DEBE_EJECUTARSE"),
            )

        get_bus().subscribe(SALE_ITEMS_PROCESS, _inventory_race, priority=100, label="sale_inventory_race_guard")
        get_bus().subscribe(SALE_ITEMS_PROCESS, _finance_should_not_run, priority=90, label="sale_finance_test")

        with pytest.raises(RuntimeError, match="inventario y caja están intactos"):
            svc.execute_sale(
                branch_id=1,
                user="cajero",
                items=[{"product_id": 1, "qty": 1, "unit_price": 10}],
                payment_method="Efectivo",
                amount_paid=10,
                client_id=1,
            )

        assert db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM detalles_venta").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM movimientos_caja").fetchone()[0] == 0
        assert db.execute("SELECT existencia FROM productos WHERE id=1").fetchone()[0] == 5.0
    finally:
        snapshot.restore()
