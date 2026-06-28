# tests/finance/test_financial_trace_waste_loyalty.py — SPJ ERP v13.4
"""Tests for FinancialTraceService.trace_waste() and trace_loyalty()."""
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


class TestTraceWaste(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.ts = _make_services(self.conn)

    def test_trace_waste_creates_journal_no_treasury(self):
        result = self.ts.trace_waste({
            "operation_id": "waste-001",
            "costo_estimado": 320.0,
            "merma_id": 7,
        })
        self.assertTrue(result["traced"])
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account, event_type, amount FROM journal_entries"
            " WHERE operation_id='waste-001-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["event_type"], "WASTE_RECORDED")
        self.assertEqual(je_row["debit_account"], "540-perdida_merma")
        self.assertEqual(je_row["credit_account"], "120-inventario")
        self.assertAlmostEqual(je_row["amount"], 320.0)
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements"
        ).fetchone()[0]
        self.assertEqual(tm_count, 0)

    def test_trace_waste_zero_skips(self):
        result = self.ts.trace_waste({
            "operation_id": "waste-002",
            "costo_estimado": 0,
            "merma_id": 8,
        })
        self.assertFalse(result["traced"])
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries"
        ).fetchone()[0]
        self.assertEqual(je_count, 0)
        log_row = self.conn.execute(
            "SELECT trace_status FROM financial_trace_log WHERE operation_id='waste-002'"
        ).fetchone()
        self.assertEqual(log_row["trace_status"], "skipped")


class TestTraceLoyalty(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.ts = _make_services(self.conn)

    def test_trace_loyalty_earned_creates_journal_no_treasury(self):
        result = self.ts.trace_loyalty({
            "operation_id": "loyalty-001",
            "monto_puntos": 50.0,
            "event": "earned",
            "cliente_id": 20,
        })
        self.assertTrue(result["traced"])
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account, event_type FROM journal_entries"
            " WHERE operation_id='loyalty-001-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["event_type"], "LOYALTY_EARNED")
        self.assertEqual(je_row["debit_account"], "570-loyalty_expense")
        self.assertEqual(je_row["credit_account"], "230-loyalty_liability")
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements"
        ).fetchone()[0]
        self.assertEqual(tm_count, 0)

    def test_trace_loyalty_redeemed_creates_journal_no_treasury(self):
        result = self.ts.trace_loyalty({
            "operation_id": "loyalty-002",
            "monto_puntos": 30.0,
            "event": "redeemed",
            "cliente_id": 21,
        })
        self.assertTrue(result["traced"])
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account, event_type FROM journal_entries"
            " WHERE operation_id='loyalty-002-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["event_type"], "LOYALTY_REDEEMED")
        self.assertEqual(je_row["debit_account"], "230-loyalty_liability")
        self.assertEqual(je_row["credit_account"], "401.1-descuento_fidelidad")
        tm_count = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements"
        ).fetchone()[0]
        self.assertEqual(tm_count, 0)


if __name__ == "__main__":
    unittest.main()
