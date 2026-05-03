
# tests/test_core_services.py — SPJ POS v12
"""
Tests para servicios core sin cobertura previa:
  - AuditService
  - AlertasService
  - AuthService
  - CierreCajaService
  - ForecastEngine
  - ComprasInventariablesEngine
  - ClienteRepository
"""
import sys, os, sqlite3, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixture base ─────────────────────────────────────────────────────────────
@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE audit_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, accion TEXT,
            modulo TEXT, entidad TEXT, entidad_id TEXT, detalles TEXT,
            fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE usuarios(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
            password_hash TEXT, salt TEXT, rol TEXT DEFAULT 'cajero',
            activo INTEGER DEFAULT 1, sucursal_id INTEGER DEFAULT 1,
            nombre TEXT);
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER DEFAULT 1);
        INSERT INTO sucursales VALUES(1,'Matriz',1);
        CREATE TABLE alertas_config(
            id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT UNIQUE,
            activa INTEGER DEFAULT 1, umbral REAL DEFAULT 0,
            canal TEXT DEFAULT 'pantalla', sucursal_id INTEGER DEFAULT 1);
        CREATE TABLE alertas_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, mensaje TEXT,
            datos TEXT, leida INTEGER DEFAULT 0, sucursal_id INTEGER DEFAULT 1,
            fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE productos(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
            precio REAL DEFAULT 0, precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 100, stock_minimo REAL DEFAULT 5,
            unidad TEXT DEFAULT 'pza', categoria TEXT,
            activo INTEGER DEFAULT 1, oculto INTEGER DEFAULT 0);
        INSERT INTO productos(nombre,precio,existencia,stock_minimo,activo)
        VALUES('Pollo kg',85,50,5,1),('Res kg',120,2,5,1);
        CREATE TABLE inventario(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER, sucursal_id INTEGER DEFAULT 1,
            existencia REAL DEFAULT 0, UNIQUE(producto_id,sucursal_id));
        INSERT INTO inventario(producto_id,sucursal_id,existencia) VALUES(1,1,50),(2,1,2);
        CREATE TABLE ventas(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, folio TEXT,
            sucursal_id INTEGER DEFAULT 1, usuario TEXT, cliente_id INTEGER,
            subtotal REAL, descuento REAL DEFAULT 0, total REAL,
            forma_pago TEXT DEFAULT 'Efectivo', efectivo_recibido REAL DEFAULT 0,
            cambio REAL DEFAULT 0, estado TEXT DEFAULT 'completada',
            fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE detalles_venta(
            id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER,
            producto_id INTEGER, cantidad REAL, precio_unitario REAL,
            descuento REAL DEFAULT 0, subtotal REAL, unidad TEXT DEFAULT 'pza');
        CREATE TABLE caja_movimientos(
            id INTEGER PRIMARY KEY AUTOINCREMENT, caja_id INTEGER DEFAULT 1,
            tipo TEXT, concepto TEXT, monto REAL, usuario TEXT,
            referencia_id INTEGER, forma_pago TEXT DEFAULT 'Efectivo',
            fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE cierres_caja(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, tipo TEXT,
            sucursal_id INTEGER, usuario TEXT, turno TEXT, fecha_apertura TEXT,
            total_ventas REAL, num_ventas INTEGER, total_efectivo REAL,
            total_tarjeta REAL, total_transferencia REAL, total_otros REAL,
            total_anulaciones REAL, num_anulaciones INTEGER, efectivo_contado REAL,
            fondo_inicial REAL, diferencia REAL, comentarios TEXT,
            fecha_cierre DATETIME DEFAULT (datetime('now')));
        CREATE TABLE turno_actual(
            id INTEGER PRIMARY KEY AUTOINCREMENT, sucursal_id INTEGER UNIQUE,
            abierto INTEGER DEFAULT 0, turno TEXT, fondo_inicial REAL DEFAULT 0,
            fecha_apertura DATETIME DEFAULT (datetime('now')));
        CREATE TABLE clientes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
            telefono TEXT, email TEXT, direccion TEXT, notas TEXT,
            codigo_fidelidad TEXT, puntos REAL DEFAULT 0, activo INTEGER DEFAULT 1,
            fecha_registro DATE, fecha_inactivacion DATE);
        CREATE TABLE compras_inventariables(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
            descripcion TEXT NOT NULL, proveedor TEXT, monto REAL NOT NULL,
            metodo_pago TEXT DEFAULT 'Efectivo', categoria TEXT DEFAULT 'equipamiento',
            sucursal_id INTEGER DEFAULT 1, usuario TEXT, activo_fijo_id INTEGER,
            notas TEXT, fecha DATETIME DEFAULT (datetime('now')));
        CREATE TABLE puntos_fidelidad(
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
            puntos REAL DEFAULT 0, venta_id INTEGER, operacion TEXT,
            fecha DATETIME DEFAULT (datetime('now')));
    """)
    yield conn
    conn.close()


# ════════════════════════════════════════════════════════════════════════════
# AuditService
# ════════════════════════════════════════════════════════════════════════════
class TestAuditService:

    def _svc(self, db):
        from repositories.audit_repository import AuditRepository
        from core.services.audit_service import AuditService
        return AuditService(AuditRepository(db))

    def test_log_change_inserta(self, db):
        svc = self._svc(db)
        svc.log_change("admin", "CREAR", "PRODUCTOS", "productos", "1",
                       detalles="producto nuevo")
        row = db.execute("SELECT * FROM audit_logs").fetchone()
        assert row is not None
        assert row["accion"] == "CREAR"
        assert row["usuario"] == "admin"

    def test_log_vacio_no_crashea(self, db):
        svc = self._svc(db)
        # Should not raise even with empty strings
        svc.log_change("", "", "", "", "")

    def test_multiples_logs(self, db):
        svc = self._svc(db)
        for i in range(5):
            svc.log_change("user", f"ACCION_{i}", "MOD", "tabla", str(i))
        count = db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        assert count == 5


# ════════════════════════════════════════════════════════════════════════════
# AlertasService
# ════════════════════════════════════════════════════════════════════════════
class TestAlertasService:

    def _svc(self, db):
        from core.services.alertas_service import AlertasService
        return AlertasService(conn=db, sucursal_id=1)

    def test_disparar_alerta_inserta_log(self, db):
        svc = self._svc(db)
        result = svc.disparar("stock_bajo", "Pollo bajo mínimo", {"producto": "Pollo"})
        assert result is True
        row = db.execute("SELECT * FROM alertas_log WHERE tipo='stock_bajo'").fetchone()
        assert row is not None

    def test_get_no_leidas_devuelve_lista(self, db):
        svc = self._svc(db)
        svc.disparar("test", "Mensaje test")
        no_leidas = svc.get_no_leidas()
        assert isinstance(no_leidas, list)
        assert len(no_leidas) >= 1

    def test_marcar_leida(self, db):
        svc = self._svc(db)
        svc.disparar("test2", "Para marcar leída")
        no_leidas = svc.get_no_leidas()
        assert len(no_leidas) > 0
        alerta_id = no_leidas[0]["id"]
        svc.marcar_leida(alerta_id)
        no_leidas_post = svc.get_no_leidas()
        ids = [r["id"] for r in no_leidas_post]
        assert alerta_id not in ids

    def test_run_checks_detecta_stock_bajo(self, db):
        svc = self._svc(db)
        # Res kg tiene existencia=2, stock_minimo=5 → debe disparar alerta
        svc.run_checks()
        row = db.execute(
            "SELECT COUNT(*) FROM alertas_log WHERE tipo='stock_bajo'"
        ).fetchone()[0]
        assert row >= 1, "Debe detectar Res kg con stock bajo"

    def test_run_checks_no_alerta_stock_normal(self, db):
        svc = self._svc(db)
        svc.run_checks()
        # Pollo kg existencia=50 > stock_minimo=5 → sin alerta
        row = db.execute(
            "SELECT COUNT(*) FROM alertas_log WHERE mensaje LIKE '%Pollo%'"
        ).fetchone()[0]
        assert row == 0, "Pollo tiene stock suficiente — sin alerta"


# ════════════════════════════════════════════════════════════════════════════
# CierreCajaService
# ════════════════════════════════════════════════════════════════════════════
class TestCierreCajaService:

    def _svc(self, db):
        from core.services.cierre_caja_service import CierreCajaService
        return CierreCajaService(conn=db, sucursal_id=1, usuario="cajero_test")

    def test_abrir_turno(self, db):
        svc = self._svc(db)
        result = svc.abrir_turno(fondo_inicial=500.0, turno="Mañana")
        assert result is not None
        assert float(result.get("fondo_inicial", 0)) == 500.0

    def test_turno_activo_despues_abrir(self, db):
        svc = self._svc(db)
        svc.abrir_turno(fondo_inicial=300.0)
        turno = svc.turno_activo()
        assert turno is not None

    def test_corte_x_sin_ventas(self, db):
        svc = self._svc(db)
        svc.abrir_turno(fondo_inicial=500.0)
        result = svc.corte_x()
        assert "total_ventas" in result
        assert float(result["total_ventas"]) == 0.0

    def test_corte_z_cierra_turno(self, db):
        svc = self._svc(db)
        svc.abrir_turno(fondo_inicial=500.0)
        result = svc.corte_z(efectivo_contado=500.0, comentarios="test")
        assert "total_ventas" in result
        # After corte Z, turno should be closed
        turno = svc.turno_activo()
        assert turno is None

    def test_corte_z_calcula_diferencia(self, db):
        svc = self._svc(db)
        svc.abrir_turno(fondo_inicial=500.0)
        result = svc.corte_z(efectivo_contado=450.0)
        # Diferencia = contado - esperado. Con 0 ventas, esperado=500 → diff=-50
        assert "diferencia" in result
        assert abs(float(result["diferencia"]) - (-50.0)) < 0.01

    def test_get_historial_devuelve_lista(self, db):
        svc = self._svc(db)
        svc.abrir_turno()
        svc.corte_z(efectivo_contado=500.0)
        hist = svc.get_historial()
        assert isinstance(hist, list)
        assert len(hist) >= 1


# ════════════════════════════════════════════════════════════════════════════
# ForecastEngine
# ════════════════════════════════════════════════════════════════════════════
class TestForecastEngine:

    def _eng(self, db):
        from core.services.forecast_engine import ForecastEngine
        return ForecastEngine(db, sucursal_id=1, horizonte=7)

    def _seed_ventas(self, db):
        vid = db.execute(
            "INSERT INTO ventas(folio,sucursal_id,usuario,subtotal,total,estado)"
            " VALUES('V1',1,'c',850,850,'completada')").lastrowid
        db.execute(
            "INSERT INTO detalles_venta(venta_id,producto_id,cantidad,precio_unitario,subtotal)"
            " VALUES(?,1,5,85,425)", (vid,))
        db.commit()

    def test_run_devuelve_lista(self, db):
        result = self._eng(db).run()
        assert isinstance(result, list)

    def test_sin_historial_demanda_cero(self, db):
        result = self._eng(db).run()
        for r in result:
            assert r["demanda_diaria"] >= 0

    def test_con_historial_demanda_positiva(self, db):
        self._seed_ventas(db)
        result = self._eng(db).run()
        pollo = next((r for r in result if "Pollo" in r["nombre"]), None)
        assert pollo is not None
        assert pollo["demanda_diaria"] > 0, "Con ventas históricas debe proyectar > 0"

    def test_requiere_pedido_stock_bajo(self, db):
        # Res kg tiene existencia=2 < stock_minimo=5
        result = self._eng(db).run()
        res = next((r for r in result if "Res" in r["nombre"]), None)
        assert res is not None
        assert res["requiere_pedido"] is True

    def test_forecast_producto_individual(self, db):
        self._seed_ventas(db)
        eng = self._eng(db)
        fc = eng.forecast_producto(1)
        assert "demanda_diaria" in fc
        assert "demanda_semana" in fc
        assert float(fc["demanda_semana"]) == pytest.approx(
            float(fc["demanda_diaria"]) * 7, abs=0.01)


# ════════════════════════════════════════════════════════════════════════════
# ComprasInventariablesEngine
# ════════════════════════════════════════════════════════════════════════════
class TestComprasInventariablesEngine:

    def _eng(self, db):
        from core.services.compras_inventariables_engine import ComprasInventariablesEngine
        return ComprasInventariablesEngine(db, usuario="admin", sucursal_id=1)

    def test_registrar_compra(self, db):
        eng = self._eng(db)
        result = eng.registrar("Báscula digital", 3500.0,
                               proveedor="Ohaus", metodo_pago="Transferencia")
        assert result["id"] > 0
        assert result["monto"] == 3500.0

    def test_descripcion_vacia_lanza_error(self, db):
        eng = self._eng(db)
        with pytest.raises(ValueError):
            eng.registrar("", 100.0)

    def test_monto_negativo_lanza_error(self, db):
        eng = self._eng(db)
        with pytest.raises(ValueError):
            eng.registrar("Mesa", -500.0)

    def test_get_compras_devuelve_registradas(self, db):
        eng = self._eng(db)
        eng.registrar("Cámara frigorífica", 25000.0)
        eng.registrar("Báscula", 3500.0)
        rows = eng.get_compras()
        assert len(rows) == 2

    def test_get_compras_filtro_categoria(self, db):
        eng = self._eng(db)
        eng.registrar("Equipo A", 1000.0, categoria="refrigeracion")
        eng.registrar("Equipo B", 2000.0, categoria="equipamiento")
        refrig = eng.get_compras(categoria="refrigeracion")
        assert len(refrig) == 1
        assert refrig[0]["descripcion"] == "Equipo A"


# ════════════════════════════════════════════════════════════════════════════
# ClienteRepository
# ════════════════════════════════════════════════════════════════════════════
class TestClienteRepository:

    def _repo(self, db):
        from repositories.cliente_repository import ClienteRepository
        return ClienteRepository(db)

    def _create(self, db, nombre="Ana García", telefono="5551234567"):
        return self._repo(db).crear(nombre, telefono)

    def test_crear_y_get_by_id(self, db):
        repo = self._repo(db)
        cid = repo.crear("Juan Pérez", "5551111111")
        cliente = repo.get_by_id(cid)
        assert cliente is not None
        assert cliente["nombre"] == "Juan Pérez"

    def test_nombre_vacio_lanza_error(self, db):
        with pytest.raises(ValueError):
            self._repo(db).crear("")

    def test_buscar_por_nombre(self, db):
        self._create(db, "Ana García")
        self._create(db, "Luis Torres")
        result = self._repo(db).buscar("ana")
        assert len(result) == 1
        assert "Ana" in result[0]["nombre"]

    def test_buscar_por_telefono(self, db):
        self._create(db, "Ana García", "5559999999")
        result = self._repo(db).buscar("5559999999")
        assert len(result) == 1

    def test_contar(self, db):
        self._create(db, "C1")
        self._create(db, "C2")
        assert self._repo(db).contar() == 2

    def test_dar_de_baja_soft_delete(self, db):
        repo = self._repo(db)
        cid = repo.crear("Para borrar")
        repo.dar_de_baja(cid)
        cliente = repo.get_by_id(cid)
        assert cliente["activo"] == 0
        assert repo.contar(solo_activos=True) == 0

    def test_actualizar_campos(self, db):
        repo = self._repo(db)
        cid = repo.crear("Nombre Viejo")
        repo.actualizar(cid, nombre="Nombre Nuevo")
        c = repo.get_by_id(cid)
        assert c["nombre"] == "Nombre Nuevo"

    def test_actualizar_puntos(self, db):
        repo = self._repo(db)
        cid = repo.crear("Cliente Puntos")
        repo.actualizar_puntos(cid, 150.0)
        c = repo.get_by_id(cid)
        assert float(c["puntos"]) == 150.0

    def test_existe(self, db):
        repo = self._repo(db)
        cid = repo.crear("Existente")
        assert repo.existe(cid) is True
        assert repo.existe(99999) is False

    def test_get_all(self, db):
        repo = self._repo(db)
        repo.crear("A"); repo.crear("B"); repo.crear("C")
        todos = repo.get_all()
        assert len(todos) == 3

    def test_stats_sin_compras(self, db):
        repo = self._repo(db)
        cid = repo.crear("Sin compras")
        stats = repo.get_stats(cid)
        assert float(stats.get("num_compras", 0)) == 0
