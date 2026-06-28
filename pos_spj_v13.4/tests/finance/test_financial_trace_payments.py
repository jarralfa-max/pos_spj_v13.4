# tests/finance/test_financial_trace_payments.py — SPJ ERP v13.4
"""Tests for FinancialTraceService.trace_payment()."""
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
    """)
    return conn


def _make_services(conn):
    from core.services.finance.journal_entry_service import JournalEntryService
    from core.services.finance.treasury_movement_service import TreasuryMovementService
    from core.services.finance.financial_trace_service import FinancialTraceService

    je = JournalEntryService(db=conn, gl_service=None)
    tm = TreasuryMovementService(db=conn, treasury_service=None)
    ts = FinancialTraceService(db=conn, journal_service=je, treasury_service=tm)
    return ts


class TestTracePayment(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.ts = _make_services(self.conn)

    def test_trace_payment_inflow(self):
        result = self.ts.trace_payment({
            "operation_id": "pay-001",
            "amount": 750.0,
            "direction": "in",
            "payment_method": "efectivo",
            "source_module": "ventas",
            "source_id": 11,
        })
        self.assertTrue(result["traced"])
        tm_row = self.conn.execute(
            "SELECT movement_type, amount FROM treasury_movements WHERE operation_id='pay-001-TM'"
        ).fetchone()
        self.assertIsNotNone(tm_row)
        self.assertEqual(tm_row["movement_type"], "inflow")
        self.assertAlmostEqual(tm_row["amount"], 750.0)
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account, event_type FROM journal_entries"
            " WHERE operation_id='pay-001-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["event_type"], "CXC_COBRADA")
        self.assertEqual(je_row["debit_account"], "110-caja")
        self.assertEqual(je_row["credit_account"], "130.1-cuentas_por_cobrar")

    def test_trace_payment_outflow(self):
        result = self.ts.trace_payment({
            "operation_id": "pay-002",
            "amount": 400.0,
            "direction": "out",
            "payment_method": "efectivo",
            "source_module": "compras",
            "source_id": 22,
        })
        self.assertTrue(result["traced"])
        tm_row = self.conn.execute(
            "SELECT movement_type FROM treasury_movements WHERE operation_id='pay-002-TM'"
        ).fetchone()
        self.assertIsNotNone(tm_row)
        self.assertEqual(tm_row["movement_type"], "outflow")
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account, event_type FROM journal_entries"
            " WHERE operation_id='pay-002-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["event_type"], "CXP_ABONADA")
        self.assertEqual(je_row["debit_account"], "210-cuentas_por_pagar")
        self.assertEqual(je_row["credit_account"], "110-caja")

    def test_trace_payment_zero_skips(self):
        result = self.ts.trace_payment({
            "operation_id": "pay-003",
            "amount": 0,
            "direction": "in",
            "payment_method": "efectivo",
            "source_module": "ventas",
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

    def test_trace_payment_idempotent(self):
        payload = {
            "operation_id": "pay-004",
            "amount": 250.0,
            "direction": "in",
            "payment_method": "efectivo",
            "source_module": "ventas",
            "source_id": 33,
        }
        self.ts.trace_payment(payload)
        self.ts.trace_payment(payload)
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements WHERE operation_id='pay-004-TM'"
        ).fetchone()[0]
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE operation_id='pay-004-JE'"
        ).fetchone()[0]
        self.assertEqual(tm_count, 1)
        self.assertEqual(je_count, 1)


if __name__ == "__main__":
    unittest.main()
