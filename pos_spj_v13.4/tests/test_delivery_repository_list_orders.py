import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from repositories.delivery_repository import DeliveryRepository


def test_list_orders_returns_rows_without_workflow_type_and_normalizes_status():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = DeliveryRepository(db)
    db.execute("CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY)")

    db.execute(
        """
        INSERT INTO delivery_orders
        (id, venta_id, folio, cliente_nombre, cliente_tel, direccion, estado, total, sucursal_id, workflow_type)
        VALUES (1, 10, 'DEL-1', 'Cliente', '555', 'Dir', 'en_camino', 100, 1, NULL)
        """
    )
    db.commit()

    rows = repo.list_orders()
    assert len(rows) == 1
    assert rows[0]["estado"] == "en_ruta"  # normalized from en_camino
    assert rows[0].get("workflow_type") is None
