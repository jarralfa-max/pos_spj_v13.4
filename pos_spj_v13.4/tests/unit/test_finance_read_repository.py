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
        CREATE TABLE cierres_caja (total_ventas REAL, total_efectivo REAL,
                                   diferencia REAL DEFAULT 0, fecha_cierre TEXT);
        CREATE TABLE ventas (total REAL, estado TEXT DEFAULT 'completada');
        CREATE TABLE compras (total REAL);
        CREATE TABLE financial_event_log (modulo TEXT, monto REAL);

        INSERT INTO financial_documents VALUES
            ('payable','pending','2000-01-01'),
            ('payable','partial','2000-02-01'),
            ('payable','paid','2000-01-01'),
            ('receivable','pending','2000-01-01');
        INSERT INTO cierres_caja VALUES
            (100.0, 100.0, 0.0,   date('now')),
            (100.0, 80.0,  -20.0, date('now')),
            (100.0, 50.0,  -50.0, '2000-01-01');
        INSERT INTO ventas VALUES (100.0,'completada'),(50.0,'completada'),(999.0,'cancelada');
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
    # Solo la diferencia (contado vs esperado) reciente cuenta; la de 2000
    # queda fuera de la ventana de 30 días. Nunca total_ventas vs efectivo.
    assert repo.count_cash_discrepancies() == 1


def test_sum_sales_excludes_anulado(repo):
    # 'anulado' no existe en el schema canónico: se filtra por estado.
    assert repo.sum_sales() == 150.0


def test_sum_purchases(repo):
    assert repo.sum_purchases() == 50.0


def test_expenses_by_module_ordered_desc(repo):
    assert repo.expenses_by_module() == [("ventas", 150.0), ("compras", 30.0)]


@pytest.fixture
def activity_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE ventas (id INTEGER PRIMARY KEY, fecha TEXT, folio TEXT, total REAL,
                             usuario TEXT, estado TEXT);
        CREATE TABLE compras (id INTEGER PRIMARY KEY, fecha TEXT, folio TEXT, total REAL,
                              usuario TEXT);
        CREATE TABLE cierres_caja (id INTEGER PRIMARY KEY, fecha_cierre TEXT, turno TEXT,
                                   total_ventas REAL, usuario TEXT);
        CREATE TABLE journal_entries (created_at TEXT, event_type TEXT, source_folio TEXT,
                                      amount REAL, user TEXT, source_module TEXT,
                                      debit_account TEXT, credit_account TEXT);
        INSERT INTO ventas VALUES (1,'2026-06-03','V-1',100.0,'ana','completada');
        INSERT INTO ventas VALUES (2,'2026-06-01','V-2',50.0,'ana','cancelada');
        INSERT INTO compras VALUES (1,'2026-06-02','C-1',40.0,'leo');
        INSERT INTO cierres_caja VALUES (1,'2026-06-04','M1',100.0,'ana');
        INSERT INTO journal_entries VALUES ('2026-06-05','asiento','JE-1',10.0,'sys','fin','a','b');
        """
    )
    conn.commit()
    return conn


def test_get_recent_activity_unions_and_orders(activity_db):
    repo = FinanceReadRepository(activity_db)
    rows = repo.get_recent_activity(limit=10)
    # cancelled sale excluded; newest first (journal 06-05, cierre 06-04, venta 06-03, compra 06-02)
    assert [r["tipo"] for r in rows] == ["asiento", "Cierre caja", "Venta", "Compra"]
    assert rows[0]["modulo"] == "Finanzas"


def test_list_journal_entries(activity_db):
    repo = FinanceReadRepository(activity_db)
    rows = repo.list_journal_entries()
    assert rows[0][1] == "asiento" and rows[0][5] == 10.0
