import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.delivery_service import DeliveryService
from repositories.delivery_repository import DeliveryRepository


class _NoopWA:
    def pull_orders(self):
        return []


def test_sync_pending_sales_to_delivery_orders_imports_and_no_duplicates():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = DeliveryRepository(db)
    db.executescript(
        """
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY,
            folio TEXT,
            cliente_nombre TEXT,
            cliente_tel TEXT,
            direccion TEXT,
            total REAL,
            sucursal_id INTEGER,
            canal TEXT,
            estado TEXT
        );
        CREATE TABLE detalles_venta (
            id INTEGER PRIMARY KEY,
            venta_id INTEGER,
            producto_id INTEGER,
            producto_nombre TEXT,
            cantidad REAL,
            precio_unitario REAL,
            subtotal REAL
        );
        """
    )
    db.execute(
        "INSERT INTO ventas(id,folio,cliente_nombre,cliente_tel,direccion,total,sucursal_id,canal,estado) "
        "VALUES (1,'WA-1','Cliente','555','Dir',100,1,'whatsapp','pendiente')"
    )
    db.execute(
        "INSERT INTO detalles_venta(venta_id,producto_id,producto_nombre,cantidad,precio_unitario,subtotal) "
        "VALUES (1,10,'Pechuga',2,50,100)"
    )
    db.commit()

    svc = DeliveryService(db=db, repository=repo, whatsapp_service=_NoopWA(), geocoding_service=None)
    imported_1 = svc.sync_pending_sales_to_delivery_orders()
    imported_2 = svc.sync_pending_sales_to_delivery_orders()

    count_orders = db.execute("SELECT COUNT(*) FROM delivery_orders WHERE venta_id=1").fetchone()[0]
    count_items = db.execute("SELECT COUNT(*) FROM delivery_items").fetchone()[0]

    assert imported_1 >= 1
    assert imported_2 >= 1  # upsert path still processes candidate row
    assert count_orders == 1
    assert count_items >= 1

