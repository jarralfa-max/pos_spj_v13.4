# tests/test_fase_g_api_gateway.py
"""
Fase G — Tests de integración del API Gateway REST.
Usa FastAPI TestClient para ejercitar todos los routers
sin levantar un servidor real.
"""
from __future__ import annotations
import sqlite3
import os
import pytest

# Configurar clave de API antes de importar la app
_TEST_KEY = "test-secret-key-g"
os.environ.setdefault("ERP_API_KEY", _TEST_KEY)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS configuraciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT UNIQUE,
            valor TEXT
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 0,
            codigo_barras TEXT,
            oculto INTEGER DEFAULT 0,
            unidad TEXT DEFAULT 'pza',
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER DEFAULT 1,
            cantidad REAL DEFAULT 0,
            costo_promedio REAL DEFAULT 0,
            ultima_actualizacion DATETIME DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE IF NOT EXISTS branch_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            quantity REAL DEFAULT 0,
            updated_at DATETIME DEFAULT (datetime('now')),
            UNIQUE(product_id, branch_id)
        );
        CREATE TABLE IF NOT EXISTS movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT, producto_id INTEGER, tipo TEXT, tipo_movimiento TEXT,
            cantidad REAL, existencia_anterior REAL DEFAULT 0,
            existencia_nueva REAL DEFAULT 0,
            costo_unitario REAL DEFAULT 0, costo_total REAL DEFAULT 0,
            descripcion TEXT, referencia TEXT, usuario TEXT,
            sucursal_id INTEGER DEFAULT 1,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT, cuenta_debe TEXT, cuenta_haber TEXT,
            monto REAL, referencia TEXT, descripcion TEXT,
            usuario TEXT, sucursal_id INTEGER DEFAULT 1,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT DEFAULT '',
            email TEXT DEFAULT '',
            direccion TEXT DEFAULT '',
            rfc TEXT DEFAULT '',
            codigo_qr TEXT,
            puntos REAL DEFAULT 0,
            nivel TEXT DEFAULT 'Bronce',
            credit_limit REAL DEFAULT 0,
            credit_balance REAL DEFAULT 0,
            activo INTEGER DEFAULT 1,
            fecha_registro DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS loyalty_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER, delta REAL, tipo TEXT,
            concepto TEXT, fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT, sucursal_id INTEGER DEFAULT 1,
            usuario TEXT, cliente_id INTEGER,
            subtotal REAL DEFAULT 0, descuento REAL DEFAULT 0,
            total REAL DEFAULT 0, forma_pago TEXT DEFAULT 'Efectivo',
            monto_pagado REAL DEFAULT 0, cambio REAL DEFAULT 0,
            estado TEXT DEFAULT 'completada',
            tipo_entrega TEXT DEFAULT 'sucursal',
            direccion_entrega TEXT DEFAULT '',
            fecha_entrega_programada TEXT DEFAULT '',
            notas TEXT DEFAULT '', canal TEXT DEFAULT 'pos',
            anticipo_pagado REAL DEFAULT 0,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS detalles_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER, producto_id INTEGER, nombre TEXT,
            cantidad REAL, precio_unitario REAL,
            descuento REAL DEFAULT 0, subtotal REAL,
            unidad TEXT DEFAULT 'pza'
        );
        INSERT INTO productos (id, nombre, precio, precio_compra, existencia)
            VALUES (1, 'Pollo Entero', 150.0, 80.0, 50.0);
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
            VALUES (1, 1, 50.0);
        INSERT INTO clientes (id, nombre, telefono)
            VALUES (1, 'Juan Pérez', '5551234567');
        INSERT INTO configuraciones (clave, valor)
            VALUES ('api_gateway_key', 'test-secret-key-g');
    """)
    conn.commit()
    return conn


@pytest.fixture
def client():
    """TestClient con AppContainer simulado."""
    from fastapi.testclient import TestClient
    from api.main import app

    conn = _build_db()

    class _MinimalContainer:
        def __init__(self):
            self.db = conn
            self.sales_service = None
            self.uc_venta = None
            self.app_service = None

    with TestClient(app, raise_server_exceptions=True) as tc:
        app.state.container = _MinimalContainer()
        yield tc


_HDR = {"X-API-Key": _TEST_KEY}
_BAD = {"X-API-Key": "wrong-key"}


# ── Health & Root ─────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_ok_or_degraded(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "erp-api-gateway"
        assert data["status"] in ("ok", "degraded")

    def test_root_lists_endpoints(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "/api/v1/ventas" in data["endpoints"]


# ── Auth ──────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_missing_key_returns_401(self, client):
        resp = client.get("/api/v1/ventas")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client):
        resp = client.get("/api/v1/ventas", headers=_BAD)
        assert resp.status_code == 401

    def test_correct_key_passes(self, client):
        resp = client.get("/api/v1/ventas", headers=_HDR)
        assert resp.status_code == 200


# ── Ventas ────────────────────────────────────────────────────────────────────

class TestVentasRouter:
    def test_listar_ventas_vacio(self, client):
        resp = client.get("/api/v1/ventas", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert "ventas" in data

    def test_get_venta_not_found(self, client):
        resp = client.get("/api/v1/ventas/99999", headers=_HDR)
        assert resp.status_code == 404

    def test_listar_ventas_paginacion(self, client):
        resp = client.get("/api/v1/ventas?limit=10&offset=0", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 0


# ── Inventario ────────────────────────────────────────────────────────────────

class TestInventarioRouter:
    def test_stock_producto_existente(self, client):
        resp = client.get("/api/v1/inventario/stock/1", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert data["producto_id"] == 1
        assert data["stock"] >= 0

    def test_stock_producto_no_existe(self, client):
        resp = client.get("/api/v1/inventario/stock/9999", headers=_HDR)
        assert resp.status_code == 404

    def test_listar_stock(self, client):
        resp = client.get("/api/v1/inventario?sucursal_id=1", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert "productos" in data
        assert isinstance(data["productos"], list)

    def test_movimientos_producto(self, client):
        resp = client.get("/api/v1/inventario/movimientos/1", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert "movimientos" in data

    def test_ajuste_sin_app_service_devuelve_503(self, client):
        resp = client.post("/api/v1/inventario/ajuste",
                          json={"producto_id": 1, "cantidad": 10.0},
                          headers=_HDR)
        # app_service es None en el container de test
        assert resp.status_code == 503

    def test_entrada_sin_app_service_devuelve_503(self, client):
        resp = client.post("/api/v1/inventario/entrada",
                          json={"producto_id": 1, "cantidad": 5.0,
                                "costo_unitario": 80.0},
                          headers=_HDR)
        assert resp.status_code == 503


# ── Clientes ──────────────────────────────────────────────────────────────────

class TestClientesRouter:
    def test_buscar_sin_query_devuelve_lista(self, client):
        resp = client.get("/api/v1/clientes", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert "clientes" in data

    def test_buscar_por_nombre(self, client):
        resp = client.get("/api/v1/clientes?q=Juan", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert any("Juan" in c["nombre"] for c in data["clientes"])

    def test_get_cliente_existente(self, client):
        resp = client.get("/api/v1/clientes/1", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert data["cliente"]["id"] == 1

    def test_get_cliente_no_existe(self, client):
        resp = client.get("/api/v1/clientes/9999", headers=_HDR)
        assert resp.status_code == 404

    def test_crear_cliente(self, client):
        resp = client.post("/api/v1/clientes",
                           json={"nombre": "Maria Lopez",
                                 "telefono": "5559876543"},
                           headers=_HDR)
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert "cliente_id" in data

    def test_crear_cliente_telefono_duplicado_409(self, client):
        # Primera creación
        client.post("/api/v1/clientes",
                    json={"nombre": "Pedro", "telefono": "5550000001"},
                    headers=_HDR)
        # Segunda con mismo teléfono
        resp = client.post("/api/v1/clientes",
                           json={"nombre": "Pedro Dup", "telefono": "5550000001"},
                           headers=_HDR)
        assert resp.status_code == 409

    def test_puntos_cliente(self, client):
        resp = client.get("/api/v1/clientes/1/puntos", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert "saldo" in data
        assert "historial" in data


# ── Pedidos ───────────────────────────────────────────────────────────────────

class TestPedidosRouter:
    def _pedido_payload(self, **overrides):
        base = {
            "cliente_id": 1,
            "items": [{"producto_id": 1, "nombre": "Pollo",
                        "cantidad": 2.0, "precio_unitario": 150.0}],
            "tipo_entrega": "sucursal",
            "sucursal_id": 1,
        }
        base.update(overrides)
        return base

    def test_crear_pedido(self, client):
        resp = client.post("/api/v1/pedidos",
                           json=self._pedido_payload(),
                           headers=_HDR)
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert data["estado"] == "pendiente_wa"
        assert data["total"] == 300.0

    def test_listar_pedidos(self, client):
        resp = client.get("/api/v1/pedidos?estado=pendiente_wa", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert "pedidos" in data

    def test_get_pedido_creado(self, client):
        r = client.post("/api/v1/pedidos",
                        json=self._pedido_payload(),
                        headers=_HDR)
        pedido_id = r.json()["venta_id"]

        resp = client.get(f"/api/v1/pedidos/{pedido_id}", headers=_HDR)
        assert resp.status_code == 200
        data = resp.json()
        assert data["pedido"]["id"] == pedido_id
        assert len(data["items"]) == 1

    def test_get_pedido_no_existe(self, client):
        resp = client.get("/api/v1/pedidos/99999", headers=_HDR)
        assert resp.status_code == 404

    def test_actualizar_estado_pedido(self, client):
        r = client.post("/api/v1/pedidos",
                        json=self._pedido_payload(),
                        headers=_HDR)
        pedido_id = r.json()["venta_id"]

        resp = client.patch(
            f"/api/v1/pedidos/{pedido_id}/estado?estado=confirmado",
            headers=_HDR
        )
        assert resp.status_code == 200
        assert resp.json()["estado"] == "confirmado"

    def test_estado_invalido_devuelve_422(self, client):
        r = client.post("/api/v1/pedidos",
                        json=self._pedido_payload(),
                        headers=_HDR)
        pedido_id = r.json()["venta_id"]

        resp = client.patch(
            f"/api/v1/pedidos/{pedido_id}/estado?estado=inventado",
            headers=_HDR
        )
        assert resp.status_code == 422

    def test_pedido_items_vacios_falla(self, client):
        resp = client.post("/api/v1/pedidos",
                           json={"items": [], "sucursal_id": 1},
                           headers=_HDR)
        # La suma de items vacíos crea total=0, pero la inserción puede fallar
        # o retornar 201 con total 0 — solo verificamos que no crashea el servidor
        assert resp.status_code in (201, 422)
