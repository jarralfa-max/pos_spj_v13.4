"""Shared fixtures for finance bounded-context integration tests."""

import sqlite3
from datetime import date

import pytest

from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.infrastructure.db.schema.finance_schema import create_finance_schema


@pytest.fixture
def finance_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_finance_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def bootstrapped_conn(finance_conn):
    bootstrap_finance(finance_conn, today=date(2026, 7, 16))
    return finance_conn


def register_supplier(conn, *, active: int = 1, blocked: int = 0,
                      bank_account: str = "012180001234567897") -> str:
    """Proveedor en el maestro canónico (``proveedores``): Finanzas valida al
    beneficiario contra él antes de programar o ejecutar un pago (F13)."""
    from backend.shared.ids import new_uuid

    conn.execute(
        "CREATE TABLE IF NOT EXISTS proveedores (id TEXT PRIMARY KEY, nombre TEXT NOT NULL,"
        " activo INTEGER DEFAULT 1, bloqueado_financiero INTEGER DEFAULT 0,"
        " motivo_bloqueo TEXT, cuenta_bancaria TEXT)")
    supplier_id = new_uuid()
    conn.execute(
        "INSERT INTO proveedores (id, nombre, activo, bloqueado_financiero, cuenta_bancaria)"
        " VALUES (?,?,?,?,?)", (supplier_id, "Proveedor de prueba", active, blocked,
                                bank_account))
    conn.commit()
    return supplier_id


def account_id(conn, code: str) -> str:
    return conn.execute("SELECT id FROM accounts WHERE code=?", (code,)).fetchone()[0]
