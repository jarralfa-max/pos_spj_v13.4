"""Protection tests for finance dashboard reads extracted from finanzas_unificadas.py."""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.repositories.finance_read_repository import (
    FinanceReadRepository,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE financial_documents (document_type TEXT, status TEXT, due_date TEXT);
        CREATE TABLE cierres_caja (total_ventas REAL, total_efectivo REAL, fecha_cierre TEXT);
        CREATE TABLE ventas (total REAL, anulado INTEGER DEFAULT 0);
        CREATE TABLE compras (total REAL);
        CREATE TABLE financial_event_log (modulo TEXT, monto REAL);

        INSERT INTO financial_documents VALUES
            ('payable','pending','2000-01-01'),
            ('payable','partial','2000-02-01'),
            ('payable','paid','2000-01-01'),
            ('receivable','pending','2000-01-01');
        INSERT INTO cierres_caja VALUES
            (100.0, 100.0, date('now')),
            (100.0, 80.0,  date('now')),
            (100.0, 50.0,  '2000-01-01');
        INSERT INTO ventas VALUES (100.0,0),(50.0,0),(999.0,1);
        INSERT INTO compras VALUES (40.0),(10.0);
        INSERT INTO financial_event_log VALUES ('ventas',100.0),('ventas',50.0),('compras',30.0);
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def repo(db):
    return FinanceReadRepository(db)


def test_count_overdue_payables(repo):
    assert repo.count_overdue_payables() == 2  # paid excluded


def test_count_overdue_receivables(repo):
    assert repo.count_overdue_receivables() == 1


def test_count_cash_discrepancies_window(repo):
    # only the recent >0.01 mismatch counts; the 2000 one is outside 30 days
    assert repo.count_cash_discrepancies() == 1


def test_sum_sales_excludes_anulado(repo):
    assert repo.sum_sales() == 150.0


def test_sum_purchases(repo):
    assert repo.sum_purchases() == 50.0


def test_expenses_by_module_ordered_desc(repo):
    assert repo.expenses_by_module() == [("ventas", 150.0), ("compras", 30.0)]
