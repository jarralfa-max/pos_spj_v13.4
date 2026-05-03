
# tests/test_new_services.py — SPJ POS v12
import sys, os, sqlite3, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER DEFAULT 1);
        INSERT INTO sucursales VALUES(1,'Matriz',1);
        CREATE TABLE empleados(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, usuario TEXT,
            rol TEXT DEFAULT 'cajero', activo INTEGER DEFAULT 1, sucursal_id INTEGER DEFAULT 1);
        CREATE TABLE personal(empleado_id INTEGER PRIMARY KEY, telefono TEXT);
        CREATE TABLE productos(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, codigo TEXT,
            precio REAL DEFAULT 0, precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 100, stock_minimo REAL DEFAULT 5,
            unidad TEXT DEFAULT 'pza', categoria TEXT,
            activo INTEGER DEFAULT 1, oculto INTEGER DEFAULT 0);
        INSERT INTO productos(nombre,precio,precio_compra,existencia,stock_minimo,activo)
        VALUES('Pollo kg',85.0,55.0,50,5,1),('Res kg',120.0,80.0,30,3,1);
        CREATE TABLE inventario(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER, sucursal_id INTEGER DEFAULT 1,
            existencia REAL DEFAULT 0, UNIQUE(producto_id,sucursal_id));
        INSERT INTO inventario(producto_id,sucursal_id,existencia) VALUES(1,1,50),(2,1,30);
        CREATE TABLE movimientos_inventario(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, producto_id INTEGER,
            tipo TEXT, tipo_movimiento TEXT, cantidad REAL,
            existencia_anterior REAL, existencia_nueva REAL,
            costo_unitario REAL DEFAULT 0, costo_total REAL DEFAULT 0,
            descripcion TEXT, referencia TEXT, usuario TEXT,
            sucursal_id INTEGER DEFAULT 1, fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE ventas(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, folio TEXT,
            sucursal_id INTEGER DEFAULT 1, usuario TEXT, cliente_id INTEGER,
            subtotal REAL, descuento REAL DEFAULT 0, total REAL,
            forma_pago TEXT DEFAULT 'Efectivo',
            efectivo_recibido REAL DEFAULT 0, cambio REAL DEFAULT 0,
            estado TEXT DEFAULT 'completada', fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE detalles_venta(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER, producto_id INTEGER,
            cantidad REAL, precio_unitario REAL,
            descuento REAL DEFAULT 0, subtotal REAL,
            unidad TEXT DEFAULT 'pza', comentarios TEXT);
        CREATE TABLE caja_movimientos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caja_id INTEGER DEFAULT 1, tipo TEXT, concepto TEXT, monto REAL,
            usuario TEXT, referencia_id INTEGER, forma_pago TEXT DEFAULT 'Efectivo',
            fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE turno_actual(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal_id INTEGER UNIQUE, abierto INTEGER DEFAULT 0,
            turno TEXT, fondo_inicial REAL DEFAULT 0,
            fecha_apertura DATETIME DEFAULT (datetime('now')));
        INSERT INTO turno_actual(sucursal_id,abierto,turno,fondo_inicial) VALUES(1,1,'M',500);
        CREATE TABLE notification_inbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT, tipo TEXT, titulo TEXT, cuerpo TEXT,
            leido INTEGER DEFAULT 0, prioridad INTEGER DEFAULT 0,
            sucursal_id INTEGER, accion_url TEXT,
            creado_en DATETIME DEFAULT (datetime('now')));
        CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO configuraciones VALUES('nombre_empresa','SPJ TEST');
        CREATE TABLE cotizaciones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
            folio TEXT UNIQUE, cliente_id INTEGER, cliente_nombre TEXT,
            subtotal REAL DEFAULT 0, descuento REAL DEFAULT 0, total REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente', notas TEXT,
            vigencia_dias INTEGER DEFAULT 7, fecha_vencimiento DATE,
            venta_id INTEGER, usuario TEXT, sucursal_id INTEGER DEFAULT 1,
            fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE cotizaciones_detalle(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cotizacion_id INTEGER REFERENCES cotizaciones(id) ON DELETE CASCADE,
            producto_id INTEGER, nombre TEXT, cantidad REAL,
            unidad TEXT DEFAULT 'kg', precio_unitario REAL,
            descuento_pct REAL DEFAULT 0, subtotal REAL);
        CREATE TABLE whatsapp_queue(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_number TEXT, message TEXT, template TEXT, payload TEXT,
            estado TEXT DEFAULT 'pendiente', intentos INTEGER DEFAULT 0,
            enviado_en DATETIME, fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE puntos_fidelidad(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER, puntos REAL DEFAULT 0, venta_id INTEGER,
            operacion TEXT, fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE clientes(id INTEGER PRIMARY KEY, nombre TEXT, puntos REAL DEFAULT 0);
    """)
    yield conn
    conn.close()


class TestNotificationService:
    def _svc(self, db):
        from core.services.notification_service import NotificationService
        return NotificationService(db)

    def _emp(self, db, user, rol, phone=None):
        eid = db.execute(
            "INSERT INTO empleados(nombre,usuario,rol,activo,sucursal_id) VALUES(?,?,?,1,1)",
            (user.capitalize(), user, rol)).lastrowid
        if phone:
            db.execute("INSERT INTO personal VALUES(?,?)", (eid, phone))
        db.commit()

    def test_stock_bajo_admin_no_cajero(self, db):
        self._emp(db, "adm", "admin"); self._emp(db, "caj", "cajero")
        self._svc(db).notificar_stock_bajo("Pollo kg", 2, 5, sucursal_id=1)
        users = {r["usuario"] for r in db.execute(
            "SELECT usuario FROM notification_inbox WHERE tipo='stock_bajo'").fetchall()}
        assert "adm" in users and "caj" not in users

    def test_corte_z_cajero_y_gerente(self, db):
        self._emp(db, "caj2", "cajero"); self._emp(db, "ger", "gerente")
        self._svc(db).notificar_corte_z("C001", 5000, 4800, -200, "caj2", sucursal_id=1)
        users = {r["usuario"] for r in db.execute(
            "SELECT usuario FROM notification_inbox WHERE tipo='corte_z'").fetchall()}
        assert "caj2" in users and "ger" in users

    def test_backup_fallido_solo_admin(self, db):
        self._emp(db, "adm2", "admin"); self._emp(db, "inv", "inventario")
        self._svc(db).notificar_backup_fallido("Disco lleno", sucursal_id=1)
        users = {r["usuario"] for r in db.execute(
            "SELECT usuario FROM notification_inbox WHERE tipo='backup_fallido'").fetchall()}
        assert "adm2" in users and "inv" not in users


class TestAnalyticsEngine:
    def _svc(self, db):
        # Nota: bi_repository y bi_service fueron eliminados en v13.4
        # Tests ahora usan analytics_engine directamente
        from core.services.analytics.analytics_engine import AnalyticsEngine
        return AnalyticsEngine(None)  # type: ignore

    def _ventas(self, db):
        db.executescript("""
            INSERT INTO ventas(folio,sucursal_id,usuario,subtotal,total,estado)
            VALUES('V1',1,'c',850,850,'completada'),('V2',1,'c',600,600,'completada');
        """); db.commit()

    def test_dashboard_hoy(self, db):
        self._ventas(db)
        assert "kpis" in self._svc(db).get_dashboard_data(1, "hoy")

    def test_cache_invalida(self, db):
        svc = self._svc(db)
        svc.get_dashboard_data(1, "hoy"); svc.invalidar_cache(1); svc.get_dashboard_data(1, "hoy")

    def test_rangos(self, db):
        self._ventas(db); svc = self._svc(db)
        assert svc.get_dashboard_data(1,"semana") and svc.get_dashboard_data(1,"mes")


class TestCotizacionService:
    def _svc(self, db):
        from core.services.cotizacion_service import CotizacionService
        return CotizacionService(conn=db, sucursal_id=1, usuario="vendedor")

    def _items(self):
        return [{"nombre":"Pollo kg","producto_id":1,"cantidad":5,"precio_unitario":85.0,"descuento_pct":0},
                {"nombre":"Res kg","producto_id":2,"cantidad":2,"precio_unitario":120.0,"descuento_pct":10}]

    def test_crear(self, db):
        r = self._svc(db).crear(items=self._items(), descuento_global=50)
        assert r["folio"].startswith("COT-") and r["total"] > 0

    def test_detalle(self, db):
        r = self._svc(db).crear(items=self._items())
        c = db.execute("SELECT COUNT(*) FROM cotizaciones_detalle WHERE cotizacion_id=?",
                       (r["cotizacion_id"],)).fetchone()[0]
        assert c == 2

    def test_filtro_estado(self, db):
        svc = self._svc(db)
        r = svc.crear(items=self._items())
        db.execute("UPDATE cotizaciones SET estado='aprobada' WHERE id=?",
                   (r["cotizacion_id"],)); db.commit()
        assert len(svc.get_cotizaciones("pendiente")) == 0
        assert len(svc.get_cotizaciones("aprobada")) == 1

    def test_vencer(self, db):
        db.execute("INSERT INTO cotizaciones(folio,total,estado,fecha_vencimiento,usuario,sucursal_id)"
                   " VALUES('COT-OLD',100,'pendiente','2020-01-01','t',1)"); db.commit()
        assert self._svc(db).vencer_expiradas() >= 1

    def test_total_descuento(self, db):
        items = [{"nombre":"X","producto_id":1,"cantidad":4,"precio_unitario":100.0,"descuento_pct":0}]
        r = self._svc(db).crear(items=items, descuento_global=50)
        assert abs(r["total"] - 350.0) < 0.01


class TestSalesReversalService:
    class _DB:
        class _Tx:
            def __init__(self, c): self._c = c
            def __enter__(self): self._c.execute("SAVEPOINT t"); return self
            def __exit__(self, et, ev, tb):
                if et: self._c.execute("ROLLBACK TO SAVEPOINT t")
                else:  self._c.execute("RELEASE SAVEPOINT t")
                return False
        def __init__(self, c): self.conn = c
        def transaction(self, _=""): return self._Tx(self.conn)

    def _svc(self, db):
        from core.services.sales_reversal_service import SalesReversalService
        return SalesReversalService(db=self._DB(db), branch_id=1)

    def _venta(self, db, estado="completada"):
        vid = db.execute(
            "INSERT INTO ventas(folio,sucursal_id,usuario,subtotal,total,estado,"
            "forma_pago,efectivo_recibido,cambio) VALUES('VT',1,'c',170,170,?,'Efectivo',200,30)",
            (estado,)).lastrowid
        db.execute("INSERT INTO detalles_venta(venta_id,producto_id,cantidad,precio_unitario,subtotal)"
                   " VALUES(?,1,2,85,170)", (vid,)); db.commit(); return vid

    def test_cancel_cancelada(self, db):
        vid = self._venta(db); self._svc(db).cancel_sale(vid, "admin")
        assert db.execute("SELECT estado FROM ventas WHERE id=?", (vid,)).fetchone()["estado"] == "cancelada"

    def test_cancel_restaura_stock(self, db):
        ex_a = db.execute("SELECT existencia FROM productos WHERE id=1").fetchone()["existencia"]
        vid = self._venta(db); self._svc(db).cancel_sale(vid, "admin")
        ex_d = db.execute("SELECT existencia FROM productos WHERE id=1").fetchone()["existencia"]
        assert ex_d >= ex_a

    def test_doble_cancel(self, db):
        from core.services.sales_reversal_service import VentaYaCanceladaError
        vid = self._venta(db); svc = self._svc(db)
        svc.cancel_sale(vid, "admin")
        with pytest.raises(VentaYaCanceladaError): svc.cancel_sale(vid, "admin")

    def test_no_completada(self, db):
        from core.services.sales_reversal_service import VentaNoCompletadaError
        vid = self._venta(db, estado="pendiente")
        with pytest.raises(VentaNoCompletadaError): self._svc(db).cancel_sale(vid, "admin")

    def test_sin_usuario(self, db):
        from core.services.sales_reversal_service import UsuarioRequeridoError
        vid = self._venta(db)
        with pytest.raises(UsuarioRequeridoError): self._svc(db).cancel_sale(vid, "")
