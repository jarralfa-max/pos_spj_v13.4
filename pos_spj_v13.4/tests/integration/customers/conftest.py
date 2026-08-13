"""Shared fixtures for Customer Master integration tests (CRM-3)."""

import sqlite3

import pytest

from backend.infrastructure.db.schema.crm_schema import create_crm_schema
from backend.infrastructure.db.schema.customer_credit_schema import create_customer_credit_schema
from backend.infrastructure.db.schema.customer_privacy_schema import (
    create_customer_privacy_schema,
)
from backend.infrastructure.db.schema.customer_service_schema import (
    create_customer_service_schema,
)
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema


@pytest.fixture
def cust_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_customers_crm_schema(conn)
    yield conn
    conn.close()



# Minimal legacy cuentas_por_cobrar shape (real columns from
# migrations/m000_base_schema.py) — CustomerAccountsReceivableSummaryQuery
# reads this table read-only; it does not own it. Same DDL as
# tests/integration/customer_credit/conftest.py's cc_conn fixture.
_CXC_DDL = """
CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
    id TEXT NOT NULL PRIMARY KEY,
    cliente_id TEXT NOT NULL,
    venta_id TEXT,
    folio TEXT,
    monto_original REAL NOT NULL,
    saldo_pendiente REAL NOT NULL,
    estado TEXT DEFAULT 'pendiente',
    sucursal_id TEXT,
    fecha DATETIME DEFAULT (datetime('now')),
    fecha_pago DATETIME
)
"""


# CRM-13: minimal legacy shapes for Ventas/Pedidos/Delivery/Fidelidad —
# each is the sanctioned read-only-summary exception, same footing as
# _CXC_DDL above. Real columns copied from migrations/m000_base_schema.py
# (pedidos_whatsapp, loyalty_snapshots) and migrations/093_create_delivery_
# core.sql (delivery_orders/delivery_order_history) — see
# backend/application/customers/queries/customer_orders_summary_query.py /
# customer_delivery_summary_query.py / loyalty_customer_summary_query.py
# for why cliente_id here never matches a real customers.id yet.
_LEGACY_OPS_DDL = """
CREATE TABLE IF NOT EXISTS pedidos_whatsapp (
    id TEXT NOT NULL PRIMARY KEY,
    numero_whatsapp TEXT NOT NULL,
    cliente_id TEXT,
    estado TEXT DEFAULT 'nuevo',
    total REAL DEFAULT 0,
    fecha DATETIME DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS delivery_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    direccion TEXT NOT NULL,
    estado TEXT DEFAULT 'pendiente',
    fecha DATETIME DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS delivery_order_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    reason TEXT,
    fecha DATETIME DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS loyalty_snapshots (
    id TEXT NOT NULL PRIMARY KEY,
    cliente_id TEXT UNIQUE,
    puntos_actuales INTEGER DEFAULT 0,
    nivel TEXT DEFAULT 'Bronce',
    visitas INTEGER DEFAULT 0,
    importe_total REAL DEFAULT 0
);
"""


@pytest.fixture
def full_crm_conn_with_ops(full_crm_conn):
    """CRM-13: full_crm_conn plus the legacy Ventas/Pedidos/Delivery/
    Fidelidad tables its integration summaries read read-only."""
    full_crm_conn.executescript(_LEGACY_OPS_DDL)
    full_crm_conn.commit()
    return full_crm_conn


@pytest.fixture
def full_crm_conn():
    """CRM-12: Customer360QueryService/CustomerHistoryQueryService read
    across every Clientes/CRM sub-bounded-context on one shared connection
    — this fixture loads all five schemas (customers, crm, customer_service,
    customer_credit, customer_privacy) together, same "everything on one
    connection" assumption ConvertLeadUseCase/AnonymizeCustomerUseCase
    already make for writes, plus the legacy ``cuentas_por_cobrar`` table
    CustomerCreditQueryService's CxC summary reads read-only.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_customers_crm_schema(conn)
    create_crm_schema(conn)
    create_customer_service_schema(conn)
    create_customer_credit_schema(conn)
    create_customer_privacy_schema(conn)
    conn.execute(_CXC_DDL)
    conn.commit()
    yield conn
    conn.close()
