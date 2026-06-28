# tests/finance/test_financial_trace_sale.py — SPJ ERP v13.4
"""Tests for FinancialTraceService.trace_sale()."""
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


class TestTraceSale(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.ts = _make_services(self.conn)

    def test_trace_sale_contado_creates_treasury_and_journal(self):
        result = self.ts.trace_sale({
            "operation_id": "sale-001",
            "total": 500.0,
            "payment_method": "Efectivo",
            "sale_id": 1,
            "folio": "V001",
        })
        self.assertTrue(result["traced"])
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements WHERE operation_id='sale-001-TM'"
        ).fetchone()[0]
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE operation_id='sale-001-JE'"
        ).fetchone()[0]
        self.assertEqual(tm_count, 1)
        self.assertEqual(je_count, 1)
        # Verify journal accounts
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account FROM journal_entries WHERE operation_id='sale-001-JE'"
        ).fetchone()
        self.assertEqual(je_row["debit_account"], "110-caja")
        self.assertEqual(je_row["credit_account"], "401.0-ingresos_ventas")

    def test_trace_sale_credito_creates_document_and_journal(self):
        result = self.ts.trace_sale({
            "operation_id": "sale-002",
            "total": 800.0,
            "payment_method": "Credito",
            "sale_id": 2,
            "folio": "V002",
            "cliente_id": 10,
        })
        self.assertTrue(result["traced"])
        fd_count = self.conn.execute(
            "SELECT COUNT(*) FROM financial_documents WHERE document_type='receivable'"
        ).fetchone()[0]
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE operation_id='sale-002-JE'"
        ).fetchone()[0]
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements"
        ).fetchone()[0]
        self.assertEqual(fd_count, 1)
        self.assertEqual(je_count, 1)
        self.assertEqual(tm_count, 0)
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account FROM journal_entries WHERE operation_id='sale-002-JE'"
        ).fetchone()
        self.assertEqual(je_row["debit_account"], "130.1-cuentas_por_cobrar")

    def test_trace_sale_mercadopago_skips_treasury(self):
        result = self.ts.trace_sale({
            "operation_id": "sale-003",
            "total": 300.0,
            "payment_method": "Mercado Pago",
            "sale_id": 3,
            "folio": "V003",
        })
        self.assertFalse(result["traced"])
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements"
        ).fetchone()[0]
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries"
        ).fetchone()[0]
        self.assertEqual(tm_count, 0)
        self.assertEqual(je_count, 0)
        log_row = self.conn.execute(
            "SELECT trace_status FROM financial_trace_log WHERE operation_id='sale-003'"
        ).fetchone()
        self.assertEqual(log_row["trace_status"], "skipped")

    def test_trace_sale_idempotent(self):
        payload = {"operation_id": "sale-004", "total": 200.0,
                   "payment_method": "Efectivo", "sale_id": 4, "folio": "V004"}
        self.ts.trace_sale(payload)
        self.ts.trace_sale(payload)
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE operation_id='sale-004-JE'"
        ).fetchone()[0]
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements WHERE operation_id='sale-004-TM'"
        ).fetchone()[0]
        self.assertEqual(je_count, 1)
        self.assertEqual(tm_count, 1)

    def test_trace_sale_zero_amount_skips(self):
        result = self.ts.trace_sale({
            "operation_id": "sale-005",
            "total": 0,
            "payment_method": "Efectivo",
            "sale_id": 5,
        })
        self.assertFalse(result["traced"])
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries"
        ).fetchone()[0]
        self.assertEqual(je_count, 0)

    def test_trace_sale_logs_to_trace_log(self):
        self.ts.trace_sale({
            "operation_id": "sale-006",
            "total": 100.0,
            "payment_method": "Efectivo",
            "sale_id": 6,
            "folio": "V006",
        })
        log_row = self.conn.execute(
            "SELECT trace_status FROM financial_trace_log WHERE operation_id='sale-006'"
        ).fetchone()
        self.assertIsNotNone(log_row)
        self.assertEqual(log_row["trace_status"], "completed")


if __name__ == "__main__":
    unittest.main()
