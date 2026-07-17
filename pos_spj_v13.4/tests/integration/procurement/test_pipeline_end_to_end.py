"""PUR-13 step 2a — end-to-end: a confirmed purchase updates PHYSICAL stock.

Proves the wired pipeline: direct-purchase confirm → procurement outbox →
dispatch → PURCHASE_STOCK_ENTRY_REGISTERED → PurchaseStockEntryHandler applies
the weighted-average stock entry. This is the guarantee that makes the QR-widget
repoint non-regressing (canonical receipts move real inventory).
"""

from decimal import Decimal

from backend.application.event_handlers.inventory.purchase_lot_entry_handler import (
    PurchaseLotEntryHandler,
)
from backend.application.event_handlers.inventory.purchase_stock_entry_handler import (
    PurchaseStockEntryHandler,
)
from backend.application.procurement.integrations.downstream_events import (
    PURCHASE_STOCK_ENTRY_REGISTERED,
)
from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
    dispatch_procurement_outbox,
)
from backend.application.procurement.integrations.wiring import wire_procurement
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
)


class Bus:
    def __init__(self):
        self._subs = {}

    def publish(self, name, payload, async_=False):
        for fn in self._subs.get(name, []):
            fn(payload)

    def subscribe(self, name, handler, priority=50, label=""):
        self._subs.setdefault(name, []).append(handler)


def _inventory_schema(conn):
    conn.execute(
        "CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY, producto_id TEXT,"
        " sucursal_id TEXT, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0,"
        " ultima_actualizacion TEXT, UNIQUE(producto_id, sucursal_id))")
    conn.execute(
        "CREATE TABLE movimientos_inventario (id TEXT PRIMARY KEY, producto_id TEXT,"
        " tipo TEXT, tipo_movimiento TEXT, cantidad REAL, costo_unitario REAL,"
        " descripcion TEXT, referencia TEXT, referencia_id TEXT, referencia_tipo TEXT,"
        " proveedor_id TEXT, usuario TEXT, sucursal_id TEXT)")
    conn.execute("CREATE TABLE productos (id TEXT PRIMARY KEY, existencia REAL DEFAULT 0,"
                 " precio_compra REAL DEFAULT 0)")
    conn.execute(
        "CREATE TABLE lotes (id TEXT PRIMARY KEY, producto_id TEXT, numero_lote TEXT,"
        " proveedor_id TEXT, fecha_recepcion DATE, fecha_caducidad DATE, peso_inicial_kg REAL,"
        " peso_actual_kg REAL, costo_kg REAL, sucursal_id TEXT, estado TEXT, temperatura_c REAL,"
        " observaciones TEXT, tipo_origen TEXT, UNIQUE(numero_lote, producto_id))")
    conn.execute("CREATE TABLE movimientos_lote (id TEXT PRIMARY KEY, lote_id TEXT, tipo TEXT,"
                 " cantidad_kg REAL, referencia TEXT, usuario TEXT)")
    conn.execute("""
        CREATE TRIGGER trg_recalc_inventario_actual
        AFTER INSERT ON movimientos_inventario
        WHEN NEW.producto_id IS NOT NULL AND NEW.sucursal_id IS NOT NULL
        BEGIN
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, ultima_actualizacion)
            VALUES (NEW.producto_id, NEW.sucursal_id,
                CASE WHEN NEW.tipo IN ('entrada','COMPRA') THEN NEW.cantidad ELSE -NEW.cantidad END,
                datetime('now'))
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                cantidad = inventario_actual.cantidad +
                    CASE WHEN NEW.tipo IN ('entrada','COMPRA') THEN NEW.cantidad ELSE -NEW.cantidad END;
        END""")
    conn.execute("INSERT INTO productos (id) VALUES ('p1')")
    conn.commit()


def test_confirmed_purchase_updates_physical_stock(proc_conn):
    _inventory_schema(proc_conn)
    bus = Bus()
    wire_procurement(bus, proc_conn)
    bus.subscribe(PURCHASE_STOCK_ENTRY_REGISTERED,
                  PurchaseStockEntryHandler(proc_conn).handle)

    created = CreateDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="e2e", supplier_id="s1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "p1", "description": "Pollo", "quantity": "10",
                "unit_cost": "30"}])
    ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="e2e-confirm", payment_source="PETTY_CASH")

    # nothing in stock until the outbox is dispatched
    assert proc_conn.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0] == 0

    dispatch_procurement_outbox(proc_conn, bus)

    row = proc_conn.execute(
        "SELECT cantidad, costo_promedio FROM inventario_actual"
        " WHERE producto_id='p1' AND sucursal_id='wh-1'").fetchone()
    assert Decimal(str(row[0])) == Decimal("10")
    assert Decimal(str(row[1])) == Decimal("30")
    existencia = proc_conn.execute("SELECT existencia FROM productos"
                                  " WHERE id='p1'").fetchone()[0]
    assert Decimal(str(existencia)) == Decimal("10")


def test_confirmed_weight_purchase_creates_lot(proc_conn):
    _inventory_schema(proc_conn)
    proc_conn.execute("INSERT INTO productos (id) VALUES ('pollo')")
    proc_conn.commit()
    bus = Bus()
    wire_procurement(bus, proc_conn)
    bus.subscribe(PURCHASE_STOCK_ENTRY_REGISTERED,
                  PurchaseStockEntryHandler(proc_conn).handle)
    bus.subscribe(PURCHASE_STOCK_ENTRY_REGISTERED,
                  PurchaseLotEntryHandler(proc_conn).handle)

    created = CreateDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", operation_id="e2e-lot", supplier_id="prov1",
        branch_id="br-1", warehouse_id="wh-1",
        lines=[{"product_id": "pollo", "description": "Pollo", "quantity": "20",
                "unit_cost": "55", "inventory_unit": "KG"}])
    ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="e2e-lot-c", payment_source="PETTY_CASH")
    dispatch_procurement_outbox(proc_conn, bus)

    # stock AND a lot (FIFO by lot) exist for the weight product
    stock = proc_conn.execute("SELECT cantidad FROM inventario_actual"
                             " WHERE producto_id='pollo'").fetchone()[0]
    lot = proc_conn.execute(
        "SELECT peso_actual_kg, costo_kg, proveedor_id, estado FROM lotes"
        " WHERE producto_id='pollo'").fetchone()
    assert Decimal(str(stock)) == Decimal("20")
    assert Decimal(str(lot[0])) == Decimal("20") and Decimal(str(lot[1])) == Decimal("55")
    assert lot[2] == "prov1" and lot[3] == "activo"
