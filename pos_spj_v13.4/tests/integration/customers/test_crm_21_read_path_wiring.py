"""CRM-21 — Migración de consumidores: the six per-area additive read-path
wiring points (WhatsApp REST, Delivery REST, Fidelidad service, Finanzas
presenter). POS/Ventas' advisory checkout call (modulos/ventas.py) is
exercised only by the repo-wide syntax check + full regression run — it is
embedded in a large PyQt5 dialog flow not worth mocking in isolation, same
triage discipline this pipeline has applied to other legacy Qt call sites.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def permissive_customer_auth(monkeypatch):
    """The three query services CRM-21 wires into WhatsApp/Delivery/
    Fidelidad (LoyaltyCustomerSummaryQuery/CustomerOrdersSummaryQuery/
    CustomerDeliverySummaryQuery) each fail closed via
    ``CustomerAuthorizationPolicy().require()`` when no PermissionChecker is
    configured — true today in production (no composition root wires one
    for the Customer Master context yet, a separate pre-existing gap none
    of this phase's call sites can close). Every CRM-21 call site
    deliberately swallows that failure and degrades to "unavailable" rather
    than raising — proven by the tests that DON'T use this fixture. This
    fixture patches ``.require()`` to a no-op only to prove the underlying
    data-fetching logic is correct *once* that separate gap is closed,
    mirroring ``permissive_for_tests()``'s intent without needing every
    CRM-21 call site to expose an injectable ``authorization`` override."""
    from backend.application.customers.authorization import CustomerAuthorizationPolicy
    monkeypatch.setattr(CustomerAuthorizationPolicy, "require", lambda self, *a, **k: None)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    create_customers_crm_schema(connection)
    connection.executescript("""
        CREATE TABLE clientes (
            id TEXT NOT NULL PRIMARY KEY, nombre TEXT NOT NULL,
            telefono TEXT, activo INTEGER DEFAULT 1
        );
        CREATE TABLE ventas (
            id TEXT NOT NULL PRIMARY KEY, folio TEXT, cliente_id TEXT,
            total REAL DEFAULT 0, estado TEXT DEFAULT 'pendiente_wa',
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE detalles_venta (
            id TEXT NOT NULL PRIMARY KEY, venta_id TEXT NOT NULL, producto_id TEXT,
            nombre TEXT, cantidad REAL, precio_unitario REAL, subtotal REAL
        );
        CREATE TABLE pedidos_whatsapp (
            id TEXT NOT NULL PRIMARY KEY, numero_whatsapp TEXT NOT NULL,
            cliente_id TEXT, estado TEXT DEFAULT 'nuevo', total REAL DEFAULT 0,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE loyalty_snapshots (
            id TEXT NOT NULL PRIMARY KEY, cliente_id TEXT UNIQUE,
            puntos_actuales INTEGER DEFAULT 0, nivel TEXT DEFAULT 'Bronce',
            visitas INTEGER DEFAULT 0, importe_total REAL DEFAULT 0
        );
        CREATE TABLE delivery_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
            direccion TEXT NOT NULL, estado TEXT DEFAULT 'pendiente',
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE delivery_order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
            reason TEXT, fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE cuentas_por_cobrar (
            id TEXT NOT NULL PRIMARY KEY, cliente_id TEXT NOT NULL, venta_id TEXT,
            folio TEXT, monto_original REAL NOT NULL, saldo_pendiente REAL NOT NULL,
            estado TEXT DEFAULT 'pendiente', sucursal_id TEXT,
            fecha DATETIME DEFAULT (datetime('now')), fecha_pago DATETIME
        );
    """)
    connection.commit()
    yield connection
    connection.close()


def _insert_cliente(conn, cliente_id: str, nombre: str = "Restaurante El Sol") -> None:
    conn.execute("INSERT INTO clientes (id, nombre, telefono, activo) VALUES (?,?,?,1)",
                (cliente_id, nombre, "+525500000000"))
    conn.commit()


class TestWhatsAppCrmSummaryEndpoint:
    def _client(self, conn) -> TestClient:
        from api.auth import verify_api_key
        from api.deps import get_db
        from api.routers.clientes import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[verify_api_key] = lambda: "test-key"
        app.dependency_overrides[get_db] = lambda: conn
        return TestClient(app)

    def test_404_for_unknown_cliente(self, conn):
        client = self._client(conn)
        resp = client.get("/api/v1/clientes/does-not-exist/crm-summary")
        assert resp.status_code == 404

    def test_degrades_gracefully_when_permission_checker_unwired(self, conn):
        """Today's real production default: no PermissionChecker is wired
        for the Customer Master context, so loyalty/orders come back None,
        but the endpoint still returns 200 with the bridge-derived name."""
        _insert_cliente(conn, "legacy-wa-0")
        client = self._client(conn)
        resp = client.get("/api/v1/clientes/legacy-wa-0/crm-summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["loyalty"] is None
        assert body["orders"] is None
        # The bridge/resolver itself has no permission gate, so the
        # friendlier name still comes through even when loyalty/orders don't.
        assert body["display_name"] == "Restaurante El Sol"
        assert body["customer_number"].startswith("CLI-")

    def test_returns_loyalty_and_orders_for_known_cliente(self, conn, permissive_customer_auth):
        _insert_cliente(conn, "legacy-wa-1")
        conn.execute(
            "INSERT INTO loyalty_snapshots (id, cliente_id, puntos_actuales, nivel, visitas,"
            " importe_total) VALUES (?,?,?,?,?,?)",
            (new_uuid(), "legacy-wa-1", 80, "Bronce", 2, 500.0))
        conn.execute(
            "INSERT INTO pedidos_whatsapp (id, numero_whatsapp, cliente_id, estado, fecha)"
            " VALUES (?,?,?,?,datetime('now'))",
            (new_uuid(), "+525500000000", "legacy-wa-1", "nuevo"))
        conn.commit()

        client = self._client(conn)
        resp = client.get("/api/v1/clientes/legacy-wa-1/crm-summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["loyalty"]["enrolled"] is True
        assert body["loyalty"]["current_points"] == 80
        assert body["orders"]["total_orders"] == 1
        # Bridge created lazily; friendlier name surfaced.
        assert body["display_name"] == "Restaurante El Sol"
        assert body["customer_number"].startswith("CLI-")


class TestDeliveryPedidoCrmSummaryField:
    def _client(self, conn) -> TestClient:
        from api.auth import verify_api_key
        from api.deps import get_db
        from api.routers.pedidos import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[verify_api_key] = lambda: "test-key"
        app.dependency_overrides[get_db] = lambda: conn
        return TestClient(app)

    def test_pedido_detail_includes_crm_delivery_summary(self, conn, permissive_customer_auth):
        _insert_cliente(conn, "legacy-del-1")
        venta_id = new_uuid()
        conn.execute(
            "INSERT INTO ventas (id, folio, cliente_id, total, estado) VALUES (?,?,?,?,?)",
            (venta_id, "WA-TEST01", "legacy-del-1", 250.0, "pendiente_wa"))
        conn.execute(
            "INSERT INTO delivery_orders (cliente_id, direccion, estado, fecha)"
            " VALUES (?,?,?,datetime('now'))", ("legacy-del-1", "Calle 1", "en_ruta"))
        conn.commit()

        client = self._client(conn)
        resp = client.get(f"/api/v1/pedidos/{venta_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["crm_delivery_summary"] is not None
        assert body["crm_delivery_summary"]["total_deliveries"] == 1

    def test_pedido_without_cliente_id_has_null_summary(self, conn):
        venta_id = new_uuid()
        conn.execute(
            "INSERT INTO ventas (id, folio, cliente_id, total, estado) VALUES (?,?,?,?,?)",
            (venta_id, "WA-TEST02", None, 100.0, "pendiente_wa"))
        conn.commit()
        client = self._client(conn)
        resp = client.get(f"/api/v1/pedidos/{venta_id}")
        assert resp.status_code == 200
        assert resp.json()["crm_delivery_summary"] is None


# `TestFidelidadClienteServiceCrmLoyaltySummary` (tested
# `core/services/cliente_service.py::ClienteService.get_crm_loyalty_summary`)
# was retired in CRM-34 along with that class — zero production callers
# (its only caller, the legacy `DialogoCliente` form, was already retired
# in CRM-24; the same loyalty summary is already shown to real users via
# `LoyaltyCustomerSummaryQuery` wired into Customer 360). See
# docs/refactor/CRM-34_legacy_purge.md.


class TestFinanzasCrmReceivableSummary:
    def test_returns_summary_for_cliente_with_open_cxc(self, conn):
        from frontend.desktop.modules.finance.finance_presenter import FinancePresenter
        _insert_cliente(conn, "legacy-fin-1")
        conn.execute(
            "INSERT INTO cuentas_por_cobrar (id, cliente_id, monto_original,"
            " saldo_pendiente, estado, fecha) VALUES (?,?,?,?,?,datetime('now'))",
            (new_uuid(), "legacy-fin-1", 1000.0, 400.0, "pendiente"))
        conn.commit()
        presenter = FinancePresenter(
            connection_provider=lambda: conn, query_services={}, use_cases={})
        summary = presenter.crm_receivable_summary("legacy-fin-1")
        assert summary is not None
        assert summary["customer_id"] == "legacy-fin-1"
        assert summary["receivable_status"] != "SIN_MOVIMIENTOS"

    def test_none_when_lookup_fails(self, conn):
        from frontend.desktop.modules.finance.finance_presenter import FinancePresenter

        def _broken_conn():
            raise RuntimeError("no connection available")

        presenter = FinancePresenter(
            connection_provider=_broken_conn, query_services={}, use_cases={})
        assert presenter.crm_receivable_summary("whatever") is None
