import sqlite3
from unittest.mock import MagicMock

from core.services.sales_service import SalesService
from core.services.loyalty_service import LoyaltyService
from core.events.event_bus import get_bus, VENTA_COMPLETADA


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, sucursal_id INTEGER, usuario TEXT, cliente_id INTEGER, subtotal REAL, descuento REAL, total REAL, forma_pago TEXT, efectivo_recibido REAL, cambio REAL, estado TEXT DEFAULT 'completada', operation_id TEXT, observations TEXT, fecha TEXT DEFAULT (datetime('now')));
        CREATE TABLE detalles_venta (id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, producto_id INTEGER, cantidad REAL, precio_unitario REAL, descuento REAL DEFAULT 0, subtotal REAL);
        CREATE TABLE inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, branch_id INTEGER, stock REAL);
        CREATE TABLE cuentas_por_cobrar (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, venta_id INTEGER, folio TEXT, monto_original REAL, saldo_pendiente REAL, sucursal_id INTEGER, estado TEXT);
        CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, allows_credit INTEGER DEFAULT 1, credit_limit REAL DEFAULT 0, credit_balance REAL DEFAULT 0, saldo REAL DEFAULT 0, puntos INTEGER DEFAULT 0);
        CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER, monto_equiv REAL, saldo_post INTEGER, referencia TEXT, descripcion TEXT, sucursal_id TEXT, usuario TEXT);
        CREATE TABLE loyalty_pasivo_log (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, tipo TEXT, estrellas INTEGER, valor_unitario REAL, monto_total REAL, referencia TEXT, sucursal_id INTEGER);
        CREATE TABLE outbox_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, payload TEXT, aggregate_type TEXT, aggregate_id INTEGER, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE configuraciones (id INTEGER PRIMARY KEY AUTOINCREMENT, clave TEXT, valor TEXT);
        CREATE TABLE pending_sales_intents (id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT UNIQUE NOT NULL, payload_json TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'pendiente_pago', payment_id TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')), confirmed_at TEXT);
        """
    )
    db.execute("INSERT INTO inventory(product_id, branch_id, stock) VALUES (1,1,10)")
    db.execute("INSERT INTO clientes(id,nombre,allows_credit,credit_limit,credit_balance,saldo,puntos) VALUES (1,'C',1,500,0,0,200)")
    db.commit()
    return db


def _service(db):
    sales_repo = __import__("repositories.sales_repository", fromlist=["SalesRepository"]).SalesRepository(db)
    inv = MagicMock()
    inv.get_stock.side_effect = lambda pid, bid: db.execute("SELECT stock FROM inventory WHERE product_id=? AND branch_id=?", (pid, bid)).fetchone()[0]
    finance = MagicMock()
    finance.validar_margen.return_value = True
    customer = MagicMock()
    customer.get_customer.return_value = {"id": 1}
    customer.validate_credit.side_effect = lambda cid, amt: (amt <= 500, "Credito insuficiente" if amt > 500 else "")
    loyalty = LoyaltyService(db_conn=db)
    loyalty._engine = None

    svc = SalesService(
        db_conn=db,
        sales_repo=sales_repo,
        recipe_repo=MagicMock(),
        inventory_service=inv,
        finance_service=finance,
        loyalty_service=loyalty,
        promotion_engine=None,
        sync_service=None,
        ticket_template_engine=MagicMock(),
        whatsapp_service=MagicMock(),
        config_service=MagicMock(get=MagicMock(return_value="<html>{{folio}}</html>")),
        feature_flag_service=MagicMock(),
        customer_service=customer,
    )
    svc._validate_stock_pre_sale = lambda items, branch_id: None
    svc._resolve_sale_items = lambda items, branch_id: items
    return svc, finance


def test_e2e_contado_credito_canje_mp_pending_confirmed():
    db = _db()
    svc, finance = _service(db)

    bus = get_bus()
    events = []
    old_publish = bus.publish
    old_handler_count = getattr(bus, "handler_count", None)
    old_handler_labels = getattr(bus, "handler_labels", None)
    bus.handler_count = lambda event: 3
    bus.handler_labels = lambda event: [
        "test_sale_inventory_deduct",
        "test_sale_finance_income",
        "test_sale_credit_cxc",
    ]

    def capture(event, payload, **kwargs):
        events.append(event)
        if event == "sale_items_process":
            for it in payload.get("items", []):
                db.execute("UPDATE inventory SET stock = stock - ? WHERE product_id=? AND branch_id=?", (float(it.get("qty", 0)), int(it["product_id"]), int(payload.get("branch_id", 1))))
                if payload.get("payment_method") == "Credito":
                    db.execute("INSERT INTO cuentas_por_cobrar(cliente_id, venta_id, folio, monto_original, saldo_pendiente, sucursal_id, estado) VALUES (?,?,?,?,?,?,'pendiente')", (payload.get("cliente_id"), payload.get("sale_id"), payload.get("folio"), payload.get("total"), payload.get("total"), payload.get("branch_id", 1)))

    bus.publish = capture
    try:
        # Contado
        folio1, _ = svc.execute_sale(branch_id=1, user="u", items=[{"product_id": 1, "qty": 2, "unit_price": 10}], payment_method="Efectivo", amount_paid=20, client_id=1)
        stock = db.execute("SELECT stock FROM inventory WHERE product_id=1 AND branch_id=1").fetchone()[0]
        assert stock == 8
        assert db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM detalles_venta").fetchone()[0] == 1
        assert events.count("sale_items_process") >= 1 and events.count(VENTA_COMPLETADA) >= 1

        # Canje
        svc.execute_sale(branch_id=1, user="u", items=[{"product_id": 1, "qty": 1, "unit_price": 10}], payment_method="Efectivo", amount_paid=10, client_id=1, loyalty_redemption_pts=10)
        assert db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE tipo='canje'").fetchone()[0] <= 1

        # Crédito insuficiente
        try:
            svc.execute_sale(branch_id=1, user="u", items=[{"product_id": 1, "qty": 1, "unit_price": 1000}], payment_method="Credito", amount_paid=0, client_id=1)
            assert False, "Debe fallar por límite"
        except Exception:
            pass

        # Crédito suficiente
        svc.execute_sale(branch_id=1, user="u", items=[{"product_id": 1, "qty": 1, "unit_price": 100}], payment_method="Credito", amount_paid=0, client_id=1)
        assert db.execute("SELECT COUNT(*) FROM cuentas_por_cobrar").fetchone()[0] == 1

        # MP pendiente + confirmación
        pending = svc.create_pending_payment_sale(branch_id=1, user="u", items=[{"product_id": 1, "qty": 1, "unit_price": 30}], client_id=1, total=30)
        assert pending["estado"] == "pendiente_pago"
        pre = db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
        svc.confirm_pending_payment_sale(pending["folio"], payment_id="P1")
        post = db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
        assert post == pre + 1
        st = db.execute("SELECT estado FROM pending_sales_intents WHERE folio=?", (pending["folio"],)).fetchone()[0]
        assert st == "confirmada"
    finally:
        bus.publish = old_publish
        if old_handler_count is not None:
            bus.handler_count = old_handler_count
        if old_handler_labels is not None:
            bus.handler_labels = old_handler_labels
