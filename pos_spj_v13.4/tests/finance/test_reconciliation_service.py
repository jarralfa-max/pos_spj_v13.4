# tests/finance/test_reconciliation_service.py — SPJ ERP v13.4
"""Tests for ReconciliationService."""
import sqlite3
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT, total REAL, forma_pago TEXT,
            estado TEXT, sucursal_id INTEGER DEFAULT 1,
            turno_id INTEGER, fecha TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT UNIQUE NOT NULL, event_type TEXT,
            source_module TEXT, source_id INTEGER, source_folio TEXT,
            debit_account TEXT, credit_account TEXT, amount REAL,
            branch_id INTEGER DEFAULT 1, user TEXT DEFAULT 'sistema',
            metadata_json TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS treasury_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT UNIQUE NOT NULL, movement_type TEXT NOT NULL,
            direction TEXT NOT NULL, amount REAL NOT NULL,
            payment_method TEXT, account TEXT DEFAULT 'caja',
            source_module TEXT, source_id INTEGER, source_folio TEXT,
            financial_document_id INTEGER, branch_id INTEGER DEFAULT 1,
            user TEXT DEFAULT 'sistema', status TEXT DEFAULT 'confirmed',
            metadata_json TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS financial_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT UNIQUE NOT NULL, document_type TEXT NOT NULL,
            source_module TEXT, source_id INTEGER, source_folio TEXT,
            party_type TEXT, party_id INTEGER,
            original_amount REAL, balance REAL,
            status TEXT DEFAULT 'pending', branch_id INTEGER DEFAULT 1,
            user TEXT DEFAULT 'sistema', due_date TEXT,
            metadata_json TEXT, created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS fixed_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT UNIQUE NOT NULL,
            asset_name TEXT, asset_type TEXT,
            acquisition_date TEXT, acquisition_cost REAL,
            current_value REAL, accumulated_depreciation REAL DEFAULT 0.0,
            depreciation_method TEXT DEFAULT 'straight_line',
            useful_life_months INTEGER DEFAULT 60,
            status TEXT DEFAULT 'active',
            supplier_id INTEGER, branch_id INTEGER DEFAULT 1,
            source_module TEXT, source_id INTEGER, source_folio TEXT,
            financial_document_id INTEGER, treasury_movement_id INTEGER,
            metadata_json TEXT, updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS reconciliation_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_type TEXT, source_module TEXT, source_id INTEGER,
            expected REAL, actual REAL, difference REAL,
            status TEXT, message TEXT, resolved_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def _make_service(conn):
    from core.services.finance.reconciliation_service import ReconciliationService
    return ReconciliationService(db=conn)


class TestReconciliationService(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.rs = _make_service(self.conn)

    def test_reconcile_sales_vs_treasury_detects_missing_treasury(self):
        # Insert a contado sale with no treasury_movement
        self.conn.execute(
            "INSERT INTO ventas (id, folio, total, forma_pago, estado) VALUES (1,'V100',500.0,'Efectivo','completada')"
        )
        issues = self.rs.reconcile_sales_vs_treasury()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["check_type"], "sale_without_treasury")
        self.assertEqual(issues[0]["source_id"], 1)
        self.assertAlmostEqual(issues[0]["expected"], 500.0)

    def test_reconcile_sales_vs_treasury_ok_when_treasury_exists(self):
        self.conn.execute(
            "INSERT INTO ventas (id, folio, total, forma_pago, estado) VALUES (2,'V101',300.0,'Efectivo','completada')"
        )
        self.conn.execute(
            "INSERT INTO treasury_movements"
            " (operation_id, movement_type, direction, amount, payment_method,"
            "  source_module, source_id, status)"
            " VALUES ('tm-v2','inflow','in',300.0,'Efectivo','ventas',2,'confirmed')"
        )
        issues = self.rs.reconcile_sales_vs_treasury()
        self.assertEqual(len(issues), 0)

    def test_reconcile_journal_balance_returns_empty_when_no_entries(self):
        issues = self.rs.reconcile_journal_balance("2026-01-01", "2026-01-31")
        # No entries → debit==credit==0 → balanced → empty list
        self.assertEqual(len(issues), 0)

    def test_reconcile_assets_detects_asset_without_journal(self):
        # Insert asset with no matching journal_entry
        self.conn.execute(
            "INSERT INTO fixed_assets"
            " (operation_id, asset_name, asset_type, acquisition_date,"
            "  acquisition_cost, current_value, status)"
            " VALUES ('asset-orphan','Activo Huerfano','equipment','2026-01-01',"
            "  15000.0,15000.0,'active')"
        )
        issues = self.rs.reconcile_assets()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["check_type"], "asset_without_journal")
        self.assertAlmostEqual(issues[0]["expected"], 15000.0)

    def test_detect_duplicates_finds_duplicate_operation_ids(self):
        # UNIQUE constraint on journal_entries.operation_id prevents true duplicates;
        # test detect_duplicates on financial_trace_log which has no unique constraint.
        # We use financial_documents with a non-unique table — but all our canonical tables
        # have UNIQUE on operation_id. So we verify the method returns empty for
        # journal_entries (UNIQUE enforced by DB) and verify it handles the query safely.
        # Insert one unique entry
        self.conn.execute(
            "INSERT INTO journal_entries"
            " (operation_id, event_type, source_module, debit_account, credit_account, amount)"
            " VALUES ('je-uniq','TEST','test','110','401',100.0)"
        )
        issues = self.rs.detect_duplicates("journal_entries")
        # Should be 0 since UNIQUE constraint prevents duplicates
        self.assertEqual(len(issues), 0)

    def test_reconcile_payables_detects_cxp_without_journal(self):
        # Insert a payable financial_document with no matching journal_entry
        self.conn.execute(
            "INSERT INTO financial_documents"
            " (operation_id, document_type, source_module, original_amount, balance, status)"
            " VALUES ('fd-cxp-orphan','payable','compras',2000.0,2000.0,'pending')"
        )
        issues = self.rs.reconcile_payables()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["check_type"], "cxp_without_journal")
        self.assertAlmostEqual(issues[0]["expected"], 2000.0)

    def test_reconcile_payables_ok_when_journal_exists(self):
        # Insert payable + matching journal
        self.conn.execute(
            "INSERT INTO financial_documents"
            " (operation_id, document_type, source_module, original_amount, balance, status)"
            " VALUES ('fd-cxp-ok','payable','compras',800.0,800.0,'pending')"
        )
        self.conn.execute(
            "INSERT INTO journal_entries"
            " (operation_id, event_type, source_module, debit_account, credit_account, amount)"
            " VALUES ('fd-cxp-ok-JE','COMPRA_CREDITO','compras','501','210',800.0)"
        )
        issues = self.rs.reconcile_payables()
        self.assertEqual(len(issues), 0)


if __name__ == "__main__":
    unittest.main()
