
# tests/conftest.py — SPJ POS v9
import sys, os, sqlite3, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def mem_db():
    """BD en memoria con esquema mínimo para tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL,
            precio REAL DEFAULT 0, precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 100, stock_minimo REAL DEFAULT 5,
            unidad TEXT DEFAULT 'pza', categoria TEXT, activo INTEGER DEFAULT 1
        );
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT, producto_id INTEGER, tipo TEXT, tipo_movimiento TEXT,
            cantidad REAL, existencia_anterior REAL, existencia_nueva REAL,
            costo_unitario REAL DEFAULT 0, costo_total REAL DEFAULT 0,
            descripcion TEXT, referencia TEXT, usuario TEXT,
            sucursal_id INTEGER DEFAULT 1, fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT, folio TEXT, sucursal_id INTEGER DEFAULT 1,
            usuario TEXT, cliente_id INTEGER,
            subtotal REAL, descuento REAL DEFAULT 0, total REAL,
            forma_pago TEXT DEFAULT 'Efectivo',
            efectivo_recibido REAL DEFAULT 0, cambio REAL DEFAULT 0,
            estado TEXT DEFAULT 'completada', fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE detalles_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER, producto_id INTEGER,
            cantidad REAL, precio_unitario REAL,
            descuento REAL DEFAULT 0, subtotal REAL,
            unidad TEXT DEFAULT 'pza', comentarios TEXT
        );
        CREATE TABLE movimientos_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT, monto REAL, descripcion TEXT,
            usuario TEXT, venta_id INTEGER, forma_pago TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER DEFAULT 1,
            cantidad REAL DEFAULT 0,
            costo_promedio REAL DEFAULT 0,
            ultima_actualizacion DATETIME DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id)
        );
        INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad)
            SELECT id, 1, existencia FROM productos;
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY, nombre TEXT, puntos INTEGER DEFAULT 0, activo INTEGER DEFAULT 1
        );
        CREATE TABLE historico_puntos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER, tipo TEXT, puntos INTEGER,
            descripcion TEXT, venta_id INTEGER, fecha DATETIME
        );
        INSERT INTO productos(id, nombre, precio, existencia, stock_minimo) VALUES
            (1, 'Pollo Entero', 150.0, 50.0, 5.0),
            (2, 'Agua 1L', 20.0, 200.0, 20.0),
            (3, 'Papas', 35.0, 10.0, 5.0),
            (4, 'Producto Sin Stock', 50.0, 0.0, 5.0);
        INSERT INTO clientes(id, nombre, puntos) VALUES (1, 'Juan Perez', 100);
    """)
    conn.commit()
    return conn

@pytest.fixture
def inv_svc(mem_db):
    from core.services.inventory.unified_inventory_service import UnifiedInventoryService
    return UnifiedInventoryService(mem_db, sucursal_id=1, usuario="test")

@pytest.fixture
def sales_svc(mem_db):
    """
    Fixture que usa el SalesService REAL (el mismo que usa producción).
    Anteriormente apuntaba a UnifiedSalesService — clase diferente que producción.
    """
    from core.services.sales_service import SalesService
    from core.services.inventory_service import InventoryService
    from core.services.loyalty_service import LoyaltyService
    from repositories.inventory_repository import InventoryRepository
    from repositories.sales_repository import SalesRepository
    from repositories.recetas import RecetaRepository as RecipeRepository

    inv_repo   = InventoryRepository(mem_db)
    sales_repo = SalesRepository(mem_db)
    recipe_repo = RecipeRepository(mem_db)

    class _FakeAudit:
        def log_change(self, **kw): pass

    class _FakeFinance:
        def register_income(self, **kw): pass

    class _FakeFlags:
        def is_enabled(self, *a, **kw): return True

    class _FakeConfig:
        def get(self, *a, **kw): return None

    class _FakeTicket:
        def generar_ticket(self, *a, **kw): return ""

    inv_svc    = InventoryService(inv_repo, _FakeAudit())
    loyalty    = LoyaltyService(mem_db)

    return SalesService(
        db_conn              = mem_db,
        sales_repo           = sales_repo,
        recipe_repo          = recipe_repo,
        inventory_service    = inv_svc,
        finance_service      = _FakeFinance(),
        loyalty_service      = loyalty,
        promotion_engine     = None,
        sync_service         = None,
        ticket_template_engine = _FakeTicket(),
        whatsapp_service     = None,
        config_service       = _FakeConfig(),
        feature_flag_service = _FakeFlags(),
    )

@pytest.fixture
def full_db():
    """BD en memoria con schema completo para tests de servicios nuevos."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE,
            password_hash TEXT, rol TEXT DEFAULT 'cajero',
            sucursal_id INTEGER DEFAULT 1, activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS personal (
            id INTEGER PRIMARY KEY, nombre TEXT, telefono TEXT, activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS notification_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER, tipo TEXT, titulo TEXT,
            cuerpo TEXT DEFAULT '', datos TEXT DEFAULT '{}',
            leido INTEGER DEFAULT 0, sucursal_id INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')), leido_at TEXT
        );
        CREATE TABLE IF NOT EXISTS whatsapp_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_number TEXT, message TEXT, estado TEXT DEFAULT 'pendiente',
            intentos INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT, folio TEXT UNIQUE, cliente_id INTEGER,
            cliente_nombre TEXT, subtotal REAL DEFAULT 0,
            descuento REAL DEFAULT 0, total REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente', notas TEXT,
            vigencia_dias INTEGER DEFAULT 7, fecha_vencimiento DATE,
            venta_id INTEGER, usuario TEXT, sucursal_id INTEGER DEFAULT 1,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS cotizaciones_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cotizacion_id INTEGER, producto_id INTEGER, nombre TEXT,
            cantidad REAL, unidad TEXT DEFAULT 'kg',
            precio_unitario REAL, descuento_pct REAL DEFAULT 0, subtotal REAL
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL,
            precio REAL DEFAULT 0, precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 100, stock_minimo REAL DEFAULT 5,
            unidad TEXT DEFAULT 'kg', activo INTEGER DEFAULT 1
        );
        INSERT INTO productos VALUES (1,'Pechuga',95.0,60.0,50.0,5.0,'kg',1);
        INSERT INTO productos VALUES (2,'Pierna',75.0,45.0,30.0,3.0,'kg',1);
        INSERT INTO personal VALUES (1,'Juan Pérez','+5215551234567',1);
        INSERT INTO usuarios VALUES (1,'Juan','juan','hash','cajero',1,1);
    """)
    return conn


@pytest.fixture
def notification_svc(full_db):
    """Fixture de NotificationService sin WhatsApp real."""
    from core.services.notification_service import NotificationService
    return NotificationService(db=full_db, whatsapp_service=None, sucursal_id=1)


@pytest.fixture
def cotizacion_svc(full_db):
    """Fixture de CotizacionService con BD en memoria."""
    from core.services.cotizacion_service import CotizacionService
    return CotizacionService(conn=full_db, sucursal_id=1, usuario="test_cajero")


@pytest.fixture
def bi_svc(full_db):
    """Fixture de BIService con repo y feature_flags stub."""
    from repositories.bi_repository import BIRepository

    class _FakeFlags:
        def require_feature(self, *a, **kw): pass
        def is_enabled(self, *a, **kw): return True

    repo = BIRepository(full_db)
    from core.services.bi_service import BIService
    return BIService(repo, _FakeFlags())
