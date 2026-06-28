# tests/finance/test_financial_trace_payroll.py — SPJ ERP v13.4
"""Tests for FinancialTraceService.trace_payroll()."""
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
            id TEXT PRIMARY KEY,
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


class TestTracePayroll(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.ts = _make_services(self.conn)

    def test_trace_payroll_generated_creates_document_and_journal(self):
        result = self.ts.trace_payroll({
            "operation_id": "nom-001",
            "total": 9500.0,
            "event": "generated",
            "nomina_id": 1,
            "empleado_id": 42,
        })
        self.assertTrue(result["traced"])
        fd_row = self.conn.execute(
            "SELECT document_type, original_amount, party_type FROM financial_documents"
            " WHERE operation_id='nom-001-FD'"
        ).fetchone()
        self.assertIsNotNone(fd_row)
        self.assertEqual(fd_row["document_type"], "payroll")
        self.assertAlmostEqual(fd_row["original_amount"], 9500.0)
        self.assertEqual(fd_row["party_type"], "employee")
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account, event_type FROM journal_entries"
            " WHERE operation_id='nom-001-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["event_type"], "PAYROLL_GENERATED")
        self.assertEqual(je_row["debit_account"], "510-nomina_expense")
        self.assertEqual(je_row["credit_account"], "220-nomina_payable")
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements"
        ).fetchone()[0]
        self.assertEqual(tm_count, 0)

    def test_trace_payroll_paid_creates_outflow_and_journal(self):
        result = self.ts.trace_payroll({
            "operation_id": "nom-002",
            "total": 8000.0,
            "event": "paid",
            "nomina_id": 2,
            "empleado_id": 43,
            "payment_method": "transferencia",
        })
        self.assertTrue(result["traced"])
        tm_row = self.conn.execute(
            "SELECT movement_type, amount FROM treasury_movements WHERE operation_id='nom-002-TM'"
        ).fetchone()
        self.assertIsNotNone(tm_row)
        self.assertEqual(tm_row["movement_type"], "outflow")
        self.assertAlmostEqual(tm_row["amount"], 8000.0)
        je_row = self.conn.execute(
            "SELECT event_type, debit_account, credit_account FROM journal_entries"
            " WHERE operation_id='nom-002-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["event_type"], "PAYROLL_PAID")
        self.assertEqual(je_row["debit_account"], "220-nomina_payable")
        self.assertEqual(je_row["credit_account"], "112-banco")
        fd_count = self.conn.execute(
            "SELECT COUNT(*) FROM financial_documents"
        ).fetchone()[0]
        self.assertEqual(fd_count, 0)

    def test_trace_payroll_idempotent(self):
        payload = {
            "operation_id": "nom-003",
            "total": 5000.0,
            "event": "paid",
            "nomina_id": 3,
            "payment_method": "efectivo",
        }
        self.ts.trace_payroll(payload)
        self.ts.trace_payroll(payload)
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements WHERE operation_id='nom-003-TM'"
        ).fetchone()[0]
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE operation_id='nom-003-JE'"
        ).fetchone()[0]
        self.assertEqual(tm_count, 1)
        self.assertEqual(je_count, 1)


if __name__ == "__main__":
    unittest.main()
