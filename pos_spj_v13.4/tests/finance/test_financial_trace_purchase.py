# tests/finance/test_financial_trace_purchase.py — SPJ ERP v13.4
"""Tests for FinancialTraceService.trace_purchase()."""
import sqlite3
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS financial_trace_log (
            id TEXT PRIMARY KEY,
            event_type TEXT, source_module TEXT, source_id INTEGER,
            source_folio TEXT, operation_id TEXT, trace_status TEXT DEFAULT 'started',
            payload_json TEXT, error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS journal_entries (
            id TEXT PRIMARY KEY,
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
            id TEXT PRIMARY KEY,
            operation_id TEXT UNIQUE NOT NULL, document_type TEXT NOT NULL,
            source_module TEXT, source_id INTEGER, source_folio TEXT,
            party_type TEXT, party_id INTEGER,
            original_amount REAL, balance REAL,
            status TEXT DEFAULT 'pending', branch_id INTEGER DEFAULT 1,
            user TEXT DEFAULT 'sistema', due_date TEXT,
            metadata_json TEXT, created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def _make_services(conn):
    from core.services.finance.journal_entry_service import JournalEntryService
    from core.services.finance.financial_document_service import FinancialDocumentService
    from core.services.finance.treasury_movement_service import TreasuryMovementService
    from core.services.finance.financial_trace_service import FinancialTraceService

    je = JournalEntryService(db=conn, gl_service=None)
    fd = FinancialDocumentService(db=conn)
    tm = TreasuryMovementService(db=conn, treasury_service=None)
    ts = FinancialTraceService(db=conn, journal_service=je, document_service=fd,
                               treasury_service=tm)
    return ts


class TestTracePurchase(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.ts = _make_services(self.conn)

    def test_trace_purchase_contado_creates_outflow_and_journal(self):
        result = self.ts.trace_purchase({
            "operation_id": "buy-001",
            "total": 1200.0,
            "payment_method": "Efectivo",
            "compra_id": 1,
            "folio": "C001",
            "proveedor_id": 5,
        })
        self.assertTrue(result["traced"])
        tm_row = self.conn.execute(
            "SELECT movement_type, amount FROM treasury_movements WHERE operation_id='buy-001-TM'"
        ).fetchone()
        self.assertIsNotNone(tm_row)
        self.assertEqual(tm_row["movement_type"], "outflow")
        self.assertAlmostEqual(tm_row["amount"], 1200.0)
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account, event_type FROM journal_entries"
            " WHERE operation_id='buy-001-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["debit_account"], "501-costo_mercancia")
        self.assertEqual(je_row["credit_account"], "110-caja")
        self.assertEqual(je_row["event_type"], "COMPRA_CONTADO")

    def test_trace_purchase_credito_creates_payable_and_journal(self):
        result = self.ts.trace_purchase({
            "operation_id": "buy-002",
            "total": 3000.0,
            "payment_method": "Credito",
            "compra_id": 2,
            "folio": "C002",
            "proveedor_id": 7,
        })
        self.assertTrue(result["traced"])
        fd_row = self.conn.execute(
            "SELECT document_type, original_amount FROM financial_documents"
            " WHERE operation_id='buy-002-FD'"
        ).fetchone()
        self.assertIsNotNone(fd_row)
        self.assertEqual(fd_row["document_type"], "payable")
        self.assertAlmostEqual(fd_row["original_amount"], 3000.0)
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements"
        ).fetchone()[0]
        self.assertEqual(tm_count, 0)
        je_row = self.conn.execute(
            "SELECT credit_account FROM journal_entries WHERE operation_id='buy-002-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["credit_account"], "210-cuentas_por_pagar")

    def test_trace_purchase_idempotent(self):
        payload = {
            "operation_id": "buy-003",
            "total": 500.0,
            "payment_method": "Efectivo",
            "compra_id": 3,
            "folio": "C003",
        }
        self.ts.trace_purchase(payload)
        self.ts.trace_purchase(payload)
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE operation_id='buy-003-JE'"
        ).fetchone()[0]
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements WHERE operation_id='buy-003-TM'"
        ).fetchone()[0]
        self.assertEqual(je_count, 1)
        self.assertEqual(tm_count, 1)

    def test_trace_purchase_zero_skips(self):
        result = self.ts.trace_purchase({
            "operation_id": "buy-004",
            "total": 0,
            "payment_method": "Efectivo",
            "compra_id": 4,
        })
        self.assertFalse(result["traced"])
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries"
        ).fetchone()[0]
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements"
        ).fetchone()[0]
        self.assertEqual(je_count, 0)
        self.assertEqual(tm_count, 0)
        log_row = self.conn.execute(
            "SELECT trace_status FROM financial_trace_log WHERE operation_id='buy-004'"
        ).fetchone()
        self.assertEqual(log_row["trace_status"], "skipped")


if __name__ == "__main__":
    unittest.main()
