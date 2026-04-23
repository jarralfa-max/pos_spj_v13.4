import sqlite3

from core.services.analytics.analytics_engine import AnalyticsEngine


def test_product_profitability_fallback_soporta_precio_compra_sin_costo():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE detalles_venta(venta_id INTEGER, producto_id INTEGER, cantidad REAL, subtotal REAL)")
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, fecha TEXT, sucursal_id INTEGER, estado TEXT)")
    db.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, precio_compra REAL)")
    db.execute("INSERT INTO ventas(id, fecha, sucursal_id, estado) VALUES (1, '2026-04-23', 1, 'completada')")
    db.execute("INSERT INTO productos(id, precio_compra) VALUES (10, 5.0)")
    db.execute("INSERT INTO detalles_venta(venta_id, producto_id, cantidad, subtotal) VALUES (1,10,2,20)")
    db.commit()

    eng = AnalyticsEngine(db)
    rows = eng.product_profitability('2026-04-01', '2026-04-30', sucursal_id=1, limit=5)

    assert rows
    assert rows[0]["producto_id"] == 10
