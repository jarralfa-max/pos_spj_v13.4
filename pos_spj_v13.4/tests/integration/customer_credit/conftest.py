"""Shared fixtures for Customer Credit integration tests (CRM-8)."""

import importlib
import sqlite3

import pytest

_run_188 = importlib.import_module(
    "migrations.standalone.188_customer_credit_bounded_context_schema").run

# Minimal legacy cuentas_por_cobrar shape (real columns from
# migrations/m000_base_schema.py) — CustomerAccountsReceivableSummaryQuery
# reads this table read-only; it does not own it.
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


@pytest.fixture
def cc_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    _run_188(conn)
    conn.execute(_CXC_DDL)
    conn.commit()
    yield conn
    conn.close()
