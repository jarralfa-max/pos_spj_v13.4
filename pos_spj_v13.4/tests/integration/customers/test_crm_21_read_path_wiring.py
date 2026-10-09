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

from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.shared.ids import new_uuid


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


# CRM-43: `TestWhatsAppCrmSummaryEndpoint` y `TestDeliveryPedidoCrmSummaryField`
# probaban `api/routers/clientes.py` y `api/routers/pedidos.py`, borrados con la
# API legacy (la API viva es `backend/api/`, sin rutas de clientes).


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
