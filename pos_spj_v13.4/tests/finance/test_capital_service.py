# tests/finance/test_capital_service.py — SPJ ERP v13.4
"""Tests para CapitalService (migración 084)."""
import sqlite3
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE capital_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movement_type TEXT NOT NULL DEFAULT 'injection',
            amount REAL NOT NULL,
            concept TEXT DEFAULT '',
            partner_name TEXT DEFAULT '',
            partner_id INTEGER,
            payment_method TEXT DEFAULT 'efectivo',
            reference TEXT DEFAULT '',
            branch_id INTEGER DEFAULT 1,
            user TEXT DEFAULT 'sistema',
            status TEXT DEFAULT 'registered',
            operation_id TEXT UNIQUE NOT NULL,
            journal_entry_id INTEGER,
            treasury_movement_id INTEGER,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE journal_entries (
            id TEXT PRIMARY KEY,
            operation_id TEXT UNIQUE NOT NULL,
            event_type TEXT, source_module TEXT, source_id INTEGER,
            source_folio TEXT, debit_account TEXT, credit_account TEXT,
            amount REAL, branch_id INTEGER DEFAULT 1,
            user TEXT DEFAULT 'sistema', metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE treasury_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT UNIQUE NOT NULL,
            movement_type TEXT NOT NULL,
            direction TEXT DEFAULT 'in',
            amount REAL NOT NULL,
            payment_method TEXT,
            account TEXT DEFAULT '',
            status TEXT DEFAULT 'confirmed',
            source_module TEXT, source_id INTEGER,
            source_folio TEXT,
            financial_document_id INTEGER,
            branch_id INTEGER DEFAULT 1,
            user TEXT DEFAULT 'sistema',
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    return conn


def _build_services(conn):
    from core.services.finance.journal_entry_service import JournalEntryService
    from core.services.finance.treasury_movement_service import TreasuryMovementService
    from core.services.finance.capital_service import CapitalService

    je = JournalEntryService(db=conn, gl_service=None)
    tm = TreasuryMovementService(db=conn, treasury_service=None)
    cap = CapitalService(db=conn, journal_service=je, treasury_service=tm)
    return cap, conn


class TestInjectCapital(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.svc, _ = _build_services(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_inject_creates_capital_row(self):
        r = self.svc.inject_capital(
            operation_id="CAP-INJ-001",
            amount=50000.0,
            concept="Aportación inicial socio A",
            partner_name="Juan Pérez",
            payment_method="transferencia",
        )
        self.assertGreater(r["capital_id"], 0)
        row = self.conn.execute(
            "SELECT * FROM capital_movements WHERE operation_id='CAP-INJ-001'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["movement_type"], "injection")
        self.assertEqual(float(row["amount"]), 50000.0)
        self.assertEqual(row["status"], "registered")

    def test_inject_creates_treasury_inflow(self):
        self.svc.inject_capital(
            operation_id="CAP-INJ-002",
            amount=30000.0,
            payment_method="efectivo",
        )
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements WHERE movement_type='inflow'"
        ).fetchone()[0]
        self.assertEqual(cnt, 1)

    def test_inject_creates_journal_entry(self):
        self.svc.inject_capital(
            operation_id="CAP-INJ-003",
            amount=20000.0,
            payment_method="efectivo",
        )
        row = self.conn.execute(
            "SELECT debit_account, credit_account FROM journal_entries WHERE operation_id='CAP-INJ-003-JE'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("caja", row["debit_account"])
        self.assertIn("capital", row["credit_account"])

    def test_inject_idempotent(self):
        r1 = self.svc.inject_capital("CAP-IDEM-1", 10000.0)
        r2 = self.svc.inject_capital("CAP-IDEM-1", 10000.0)
        self.assertEqual(r1["capital_id"], r2["capital_id"])
        cnt = self.conn.execute("SELECT COUNT(*) FROM capital_movements").fetchone()[0]
        self.assertEqual(cnt, 1)


class TestWithdrawCapital(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.svc, _ = _build_services(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_withdraw_creates_capital_row(self):
        r = self.svc.withdraw_capital(
            operation_id="CAP-WIT-001",
            amount=5000.0,
            concept="Retiro mensual socio",
            partner_name="Ana López",
        )
        self.assertGreater(r["capital_id"], 0)
        row = self.conn.execute(
            "SELECT movement_type FROM capital_movements WHERE operation_id='CAP-WIT-001'"
        ).fetchone()
        self.assertEqual(row["movement_type"], "withdrawal")

    def test_withdraw_creates_treasury_outflow(self):
        self.svc.withdraw_capital("CAP-WIT-002", 3000.0)
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM treasury_movements WHERE movement_type='outflow'"
        ).fetchone()[0]
        self.assertEqual(cnt, 1)

    def test_withdraw_journal_debits_retiros(self):
        self.svc.withdraw_capital("CAP-WIT-003", 2000.0)
        row = self.conn.execute(
            "SELECT debit_account FROM journal_entries WHERE operation_id='CAP-WIT-003-JE'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("retiros", row["debit_account"])


class TestGetSummary(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.svc, _ = _build_services(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_summary_empty_returns_zeros(self):
        s = self.svc.get_summary()
        self.assertEqual(s["capital_actual"], 0.0)
        self.assertEqual(s["total_inyectado"], 0.0)

    def test_summary_after_injection(self):
        self.svc.inject_capital("CAP-SUM-1", 100000.0)
        s = self.svc.get_summary()
        self.assertEqual(s["total_inyectado"], 100000.0)
        self.assertEqual(s["capital_actual"], 100000.0)

    def test_summary_injection_minus_withdrawal(self):
        self.svc.inject_capital("CAP-SUM-2", 100000.0)
        self.svc.withdraw_capital("CAP-SUM-3", 25000.0)
        s = self.svc.get_summary()
        self.assertEqual(s["capital_actual"], 75000.0)
        self.assertEqual(s["total_inyectado"], 100000.0)
        self.assertEqual(s["total_retirado"], 25000.0)

    def test_get_history_returns_movements(self):
        self.svc.inject_capital("CAP-HIST-1", 50000.0, partner_name="Socio A")
        self.svc.withdraw_capital("CAP-HIST-2", 10000.0)
        history = self.svc.get_history()
        self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
