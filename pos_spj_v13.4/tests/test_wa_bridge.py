# tests/test_wa_bridge.py — SPJ POS v13.5
"""
Tests unitarios para ERPBridge (whatsapp_service/erp/bridge.py).
Usa una BD SQLite en memoria para aislar el puente del ERP real.
"""
import sys, os

# ── WA service sys.path setup (antes de cualquier import WA) ─────────────────
import importlib.util as _ilu
_WA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../whatsapp_service'))
# Remover 'config' conflictivo (pos_spj_v13.4/config.py) antes de cargar WA
for _k in list(sys.modules.keys()):
    if _k == 'config' or _k.startswith('config.'):
        del sys.modules[_k]
if _WA_ROOT not in sys.path:
    sys.path.insert(0, _WA_ROOT)
sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Force-load the WA config package so imports find the right module
_cfg_spec = _ilu.spec_from_file_location('config', os.path.join(_WA_ROOT, 'config', '__init__.py'))
_cfg_mod = _ilu.module_from_spec(_cfg_spec); sys.modules['config'] = _cfg_mod; _cfg_spec.loader.exec_module(_cfg_mod)
_set_spec = _ilu.spec_from_file_location('config.settings', os.path.join(_WA_ROOT, 'config', 'settings.py'))
_set_mod = _ilu.module_from_spec(_set_spec); sys.modules['config.settings'] = _set_mod; _set_spec.loader.exec_module(_set_mod)
_cfg_mod.settings = _set_mod

import sqlite3
import pytest

# ── Schema mínimo ─────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sucursales (
    id INTEGER PRIMARY KEY, nombre TEXT, direccion TEXT, activa INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, telefono TEXT,
    activo INTEGER DEFAULT 1,
    credit_limit REAL DEFAULT 0, credit_balance REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY, nombre TEXT, precio REAL DEFAULT 0,
    existencia REAL DEFAULT 10, activo INTEGER DEFAULT 1, oculto INTEGER DEFAULT 0,
    unidad TEXT DEFAULT 'kg', categoria TEXT DEFAULT 'Carne'
);
CREATE TABLE IF NOT EXISTS branch_inventory (
    product_id INTEGER, branch_id INTEGER, quantity REAL
);
CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, cliente_id INTEGER,
    total REAL, estado TEXT DEFAULT 'pendiente_wa', sucursal_id INTEGER DEFAULT 1,
    tipo_entrega TEXT DEFAULT 'sucursal', direccion_entrega TEXT,
    fecha_entrega_programada TEXT, notas TEXT, canal TEXT DEFAULT 'whatsapp',
    fecha TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS detalle_ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER, producto_id INTEGER, nombre TEXT,
    cantidad REAL, precio_unitario REAL, subtotal REAL,
    unidad TEXT DEFAULT 'kg'
);
CREATE TABLE IF NOT EXISTS cotizaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, cliente_id INTEGER,
    cliente_nombre TEXT, total REAL, estado TEXT DEFAULT 'pendiente',
    usuario TEXT, sucursal_id INTEGER DEFAULT 1, fecha TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cotizaciones_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cotizacion_id INTEGER,
    producto_id INTEGER, nombre TEXT,
    cantidad REAL, precio_unitario REAL, subtotal REAL
);
CREATE TABLE IF NOT EXISTS anticipos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER, monto REAL, metodo TEXT DEFAULT 'mercadopago',
    estado TEXT DEFAULT 'pendiente', fecha TEXT DEFAULT (datetime('now'))
);
"""

_SEED = """
INSERT INTO sucursales VALUES (1,'Sucursal Central','Calle 1',1);
INSERT INTO sucursales VALUES (2,'Sucursal Norte','Calle 2',1);
INSERT INTO clientes VALUES (1,'María López','5551234567',1,2000.0,500.0);
INSERT INTO clientes VALUES (2,'Pedro Martínez','5559876543',1,0,0);
INSERT INTO productos VALUES (1,'Pechuga de Pollo',95.0,10.0,1,0,'kg','Carne');
INSERT INTO productos VALUES (2,'Pierna de Pollo',75.0,8.0,1,0,'kg','Carne');
INSERT INTO productos VALUES (3,'Chuleta de Cerdo',85.0,5.0,1,0,'kg','Cerdo');
INSERT INTO productos VALUES (4,'Producto Oculto',50.0,10.0,1,1,'kg','Carne');
INSERT INTO branch_inventory VALUES (1,1,12.5);
INSERT INTO branch_inventory VALUES (2,1,7.0);
"""


@pytest.fixture
def bridge(tmp_path):
    """ERPBridge con BD en archivo temporal."""
    from erp.bridge import ERPBridge

    db_file = str(tmp_path / "test.db")
    b = ERPBridge(db_file)
    b.db.executescript(_SCHEMA + _SEED)
    return b


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGetSucursales:
    def test_returns_active_only(self, bridge):
        rows = bridge.get_sucursales()
        assert len(rows) == 2

    def test_returns_nombre_field(self, bridge):
        rows = bridge.get_sucursales()
        names = {r["nombre"] for r in rows}
        assert "Sucursal Central" in names


class TestFindClienteByPhone:
    def test_finds_by_last_10_digits(self, bridge):
        result = bridge.find_cliente_by_phone("525551234567")
        assert result is not None
        assert result["nombre"] == "María López"

    def test_returns_none_when_not_found(self, bridge):
        result = bridge.find_cliente_by_phone("0000000000")
        assert result is None

    def test_credito_disponible_in_result(self, bridge):
        result = bridge.find_cliente_by_phone("5551234567")
        assert result["credito_disponible"] == 1500.0


class TestCreateClienteMinimo:
    def test_inserts_and_returns_id(self, bridge):
        new_id = bridge.create_cliente_minimo("Nuevo WA", "5550001111")
        assert isinstance(new_id, int) and new_id > 0

    def test_cliente_is_findable_after_creation(self, bridge):
        bridge.create_cliente_minimo("WA Test", "5550002222")
        result = bridge.find_cliente_by_phone("5550002222")
        assert result is not None and result["nombre"] == "WA Test"


class TestGetCreditoDisponible:
    def test_calculates_credito(self, bridge):
        assert bridge.get_credito_disponible(1) == 1500.0

    def test_returns_zero_for_no_credit(self, bridge):
        assert bridge.get_credito_disponible(2) == 0.0


class TestGetProductosByCategory:
    def test_filters_by_categoria(self, bridge):
        items = bridge.get_productos_by_category("Carne", 1)
        names = [i["nombre"] for i in items]
        assert "Pechuga de Pollo" in names
        assert "Chuleta de Cerdo" not in names

    def test_excludes_oculto(self, bridge):
        items = bridge.get_productos_by_category("Carne", 1)
        names = [i["nombre"] for i in items]
        assert "Producto Oculto" not in names

    def test_uses_branch_inventory_quantity(self, bridge):
        items = bridge.get_productos_by_category("Carne", 1)
        pechuga = next(i for i in items if i["nombre"] == "Pechuga de Pollo")
        assert pechuga["stock"] == 12.5


class TestGetCategorias:
    def test_returns_distinct_categories(self, bridge):
        cats = bridge.get_categorias(1)
        assert "Carne" in cats

    def test_no_duplicates(self, bridge):
        cats = bridge.get_categorias(1)
        assert len(cats) == len(set(cats))


class TestCrearPedidoWA:
    def test_creates_venta_and_items(self, bridge):
        items = [{"producto_id": 1, "nombre": "Pechuga", "cantidad": 2.0, "precio_unitario": 95.0}]
        result = bridge.crear_pedido_wa(items, 1, 1, "sucursal")
        assert result["total"] == 190.0 and result["folio"].startswith("WA-")

    def test_folio_unique(self, bridge):
        items = [{"producto_id": 1, "nombre": "P", "cantidad": 1, "precio_unitario": 50}]
        r1 = bridge.crear_pedido_wa(items, 1, 1, "sucursal")
        r2 = bridge.crear_pedido_wa(items, 1, 1, "sucursal")
        assert r1["folio"] != r2["folio"]


class TestGetUltimoPedido:
    def test_returns_none_when_no_orders(self, bridge):
        assert bridge.get_ultimo_pedido(2) is None

    def test_returns_last_order(self, bridge):
        items = [{"producto_id": 1, "nombre": "P", "cantidad": 1, "precio_unitario": 50}]
        bridge.crear_pedido_wa(items, 1, 1, "sucursal")
        result = bridge.get_ultimo_pedido(1)
        assert result is not None and "folio" in result


class TestGetEstadoPedido:
    def test_returns_estado_by_folio(self, bridge):
        items = [{"producto_id": 1, "nombre": "P", "cantidad": 1, "precio_unitario": 50}]
        res = bridge.crear_pedido_wa(items, 1, 1, "sucursal")
        estado = bridge.get_estado_pedido(res["folio"])
        assert estado is not None and estado["estado"] == "pendiente_wa"

    def test_returns_none_for_unknown_folio(self, bridge):
        assert bridge.get_estado_pedido("UNKNOWN-000") is None


class TestCalcularAnticipoRules:
    def test_requires_anticipo_when_no_credit(self, bridge):
        assert bridge.requiere_anticipo(2, total=500.0, programado=False) is True

    def test_no_anticipo_when_credit_covers(self, bridge):
        assert bridge.requiere_anticipo(1, total=100.0, programado=False) is False

    def test_programado_always_requires_anticipo(self, bridge):
        assert bridge.requiere_anticipo(1, total=10.0, programado=True) is True


class TestRegistrarAnticipo:
    def test_inserts_row(self, bridge):
        items = [{"producto_id": 1, "nombre": "P", "cantidad": 1, "precio_unitario": 50}]
        venta = bridge.crear_pedido_wa(items, 1, 1, "sucursal")
        ap_id = bridge.registrar_anticipo(venta["venta_id"], monto=200.0)
        assert isinstance(ap_id, int) and ap_id > 0
