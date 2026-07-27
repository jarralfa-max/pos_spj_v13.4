from core.services.driver_service import DriverService


def _db():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE drivers(id INTEGER PRIMARY KEY,nombre TEXT,telefono TEXT,vehiculo TEXT,activo INTEGER,en_ruta INTEGER,sucursal_id INTEGER,usuario_id INTEGER)")
    conn.execute("CREATE TABLE delivery_orders(id INTEGER PRIMARY KEY,estado TEXT,workflow_type TEXT,driver_id INTEGER,fecha_asignacion TEXT)")
    conn.execute("CREATE TABLE delivery_order_history(id INTEGER PRIMARY KEY,order_id INTEGER,estado_anterior TEXT,estado_nuevo TEXT,usuario TEXT,observacion TEXT)")
    return conn


def test_list_active_drivers_by_branch():
    db = _db()
    db.execute("INSERT INTO drivers VALUES(1,'A','','',1,0,1,NULL)")
    db.execute("INSERT INTO drivers VALUES(2,'B','','',1,0,2,NULL)")
    db.execute("INSERT INTO drivers VALUES(3,'C','','',0,0,1,NULL)")
    svc = DriverService(db)
    rows = svc.list_active_drivers(1)
    assert [r['id'] for r in rows] == [1]


def test_assign_validation_counter_blocked():
    db = _db()
    db.execute("INSERT INTO drivers VALUES(1,'A','','',1,0,1,NULL)")
    db.execute("INSERT INTO delivery_orders VALUES(10,'preparacion','counter',NULL,NULL)")
    svc = DriverService(db)
    try:
        svc.assign_driver(10, 1, branch_id=1)
        assert False
    except ValueError as e:
        assert 'Mostrador' in str(e)


def test_assign_success_delivery_preparacion():
    db = _db()
    db.execute("INSERT INTO drivers VALUES(1,'A','','',1,0,1,NULL)")
    db.execute("INSERT INTO delivery_orders VALUES(10,'preparacion','delivery',NULL,NULL)")
    svc = DriverService(db)
    svc.assign_driver(10, 1, branch_id=1)
    row = db.execute("SELECT driver_id FROM delivery_orders WHERE id=10").fetchone()
    assert row[0] == 1
    h = db.execute("SELECT observacion FROM delivery_order_history WHERE order_id=10").fetchone()
    assert 'Repartidor asignado' in h[0]
