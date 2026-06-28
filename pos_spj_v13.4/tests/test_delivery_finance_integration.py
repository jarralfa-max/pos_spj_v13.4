"""Tests for delivery defects 11, 13, 14 — Caja + Finanzas integration.

Defect 11/14: DELIVERY_TOTAL_FINALIZED → delivery revenue recognized once in GL.
Defect 13: DRIVER_SETTLEMENT_CREATED → treasury cash reconciliation (cash in,
shortage/surplus, commission), idempotent by cut_id.
"""
from __future__ import annotations

import sqlite3

import pytest

from core.events.handlers.delivery_finance_handler import DeliveryRevenueFinanceHandler
from core.events.handlers.delivery_handler import DriverSettlementFinanceHandler


# ── Shared in-memory finance schema ──────────────────────────────────────────

@pytest.fixture
def fin_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE financial_event_log (
            id TEXT PRIMARY KEY,
            evento TEXT, modulo TEXT, referencia_id INTEGER, monto REAL,
            cuenta_debe TEXT, cuenta_haber TEXT, usuario_id TEXT,
            sucursal_id INTEGER, metadata TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE treasury_ledger (
            id TEXT PRIMARY KEY,
            tipo TEXT, categoria TEXT, concepto TEXT,
            ingreso REAL DEFAULT 0, egreso REAL DEFAULT 0,
            sucursal_id INTEGER, referencia TEXT, usuario TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accion TEXT, modulo TEXT, entidad TEXT, entidad_id TEXT,
            usuario TEXT, sucursal_id INTEGER, detalles TEXT, fecha TEXT
        )"""
    )
    conn.commit()
    return conn


# ── Defect 11/14: revenue recognition ────────────────────────────────────────

def test_revenue_handler_posts_gl_entry(fin_db):
    h = DeliveryRevenueFinanceHandler(fin_db)
    h.handle({
        "order_id": 42, "final_total": 250.0, "branch_id": 1,
        "payment_method": "Efectivo al entregar", "folio": "DEL-42", "balance_due": 0,
    })
    rows = fin_db.execute(
        "SELECT evento, monto, cuenta_haber FROM financial_event_log WHERE evento='VENTA_DELIVERY'"
    ).fetchall()
    assert len(rows) == 1
    assert abs(rows[0][1] - 250.0) < 1e-9
    assert rows[0][2] == "401.0-ingresos-ventas"


def test_revenue_handler_idempotent(fin_db):
    """Defect 11: re-firing the same order does not double-book revenue."""
    h = DeliveryRevenueFinanceHandler(fin_db)
    payload = {"order_id": 42, "final_total": 250.0, "branch_id": 1, "folio": "DEL-42"}
    h.handle(payload)
    h.handle(payload)
    rows = fin_db.execute(
        "SELECT COUNT(*) FROM financial_event_log WHERE evento='VENTA_DELIVERY'"
    ).fetchone()
    assert rows[0] == 1


def test_revenue_handler_skips_zero_total(fin_db):
    h = DeliveryRevenueFinanceHandler(fin_db)
    h.handle({"order_id": 1, "final_total": 0.0, "branch_id": 1})
    rows = fin_db.execute("SELECT COUNT(*) FROM financial_event_log").fetchone()
    assert rows[0] == 0


# ── Defect 13: driver settlement treasury reconciliation ─────────────────────

def test_settlement_posts_cash_income(fin_db):
    h = DriverSettlementFinanceHandler(fin_db)
    h.handle({
        "cut_id": "cut-1", "driver_nombre": "Juan",
        "efectivo_entregado": 500.0, "diferencia": 0.0, "sucursal_id": 1,
    })
    row = fin_db.execute(
        "SELECT ingreso FROM treasury_ledger WHERE categoria='delivery_corte_efectivo' AND referencia='cut-1'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - 500.0) < 1e-9


def test_settlement_posts_shortage_as_egreso(fin_db):
    h = DriverSettlementFinanceHandler(fin_db)
    h.handle({
        "cut_id": "cut-2", "driver_nombre": "Ana",
        "efectivo_entregado": 480.0, "diferencia": -20.0, "sucursal_id": 1,
    })
    row = fin_db.execute(
        "SELECT egreso FROM treasury_ledger WHERE categoria='delivery_faltante' AND referencia='cut-2'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - 20.0) < 1e-9


def test_settlement_posts_surplus_as_ingreso(fin_db):
    h = DriverSettlementFinanceHandler(fin_db)
    h.handle({
        "cut_id": "cut-3", "driver_nombre": "Ana",
        "efectivo_entregado": 520.0, "diferencia": 20.0, "sucursal_id": 1,
    })
    row = fin_db.execute(
        "SELECT ingreso FROM treasury_ledger WHERE categoria='delivery_sobrante' AND referencia='cut-3'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - 20.0) < 1e-9


def test_settlement_posts_commission_as_egreso(fin_db):
    h = DriverSettlementFinanceHandler(fin_db)
    h.handle({
        "cut_id": "cut-4", "driver_nombre": "Luis",
        "efectivo_entregado": 300.0, "diferencia": 0.0, "comision": 45.0, "sucursal_id": 1,
    })
    row = fin_db.execute(
        "SELECT egreso FROM treasury_ledger WHERE categoria='delivery_comision' AND referencia='cut-4'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - 45.0) < 1e-9


def test_settlement_idempotent_no_double_post(fin_db):
    """Defect 13: re-firing the same cut does not double-post to treasury."""
    h = DriverSettlementFinanceHandler(fin_db)
    payload = {
        "cut_id": "cut-5", "driver_nombre": "Juan",
        "efectivo_entregado": 500.0, "diferencia": 0.0, "sucursal_id": 1,
    }
    h.handle(payload)
    h.handle(payload)
    rows = fin_db.execute(
        "SELECT COUNT(*) FROM treasury_ledger WHERE referencia='cut-5'"
    ).fetchone()
    assert rows[0] == 1


def test_settlement_posts_gl_entry(fin_db):
    """Defect 14: the settlement also books a GL journal entry."""
    h = DriverSettlementFinanceHandler(fin_db)
    h.handle({
        "cut_id": "cut-6", "driver_nombre": "Juan",
        "efectivo_entregado": 500.0, "diferencia": 0.0, "sucursal_id": 1,
    })
    row = fin_db.execute(
        "SELECT cuenta_debe, cuenta_haber FROM financial_event_log WHERE evento='DRIVER_SETTLEMENT_CREATED'"
    ).fetchone()
    assert row is not None
    assert row[0] == "caja_delivery"
    assert row[1] == "cuentas_repartidores"


# ── No double counting between the two ledgers ───────────────────────────────

def test_revenue_and_settlement_use_different_ledgers(fin_db):
    """Revenue → GL; settlement cash → treasury. They must not overlap."""
    DeliveryRevenueFinanceHandler(fin_db).handle(
        {"order_id": 7, "final_total": 100.0, "branch_id": 1, "folio": "DEL-7"}
    )
    DriverSettlementFinanceHandler(fin_db).handle(
        {"cut_id": "cut-7", "driver_nombre": "X", "efectivo_entregado": 100.0,
         "diferencia": 0.0, "sucursal_id": 1}
    )
    # Revenue lives only in financial_event_log (VENTA_DELIVERY)
    rev = fin_db.execute(
        "SELECT COUNT(*) FROM financial_event_log WHERE evento='VENTA_DELIVERY'"
    ).fetchone()[0]
    # Cash reconciliation lives only in treasury_ledger
    cash = fin_db.execute(
        "SELECT COUNT(*) FROM treasury_ledger WHERE categoria='delivery_corte_efectivo'"
    ).fetchone()[0]
    assert rev == 1
    assert cash == 1
