# tests/finance/test_financial_trace_operating_supplies.py — SPJ ERP v13.4
"""Tests for OperatingSuppliesService."""
import sqlite3
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
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
        CREATE TABLE IF NOT EXISTS operating_supplies (
            id TEXT PRIMARY KEY,
            operation_id TEXT UNIQUE NOT NULL, supply_type TEXT,
            description TEXT, quantity REAL DEFAULT 1.0,
            unit_cost REAL, total_amount REAL,
            status TEXT DEFAULT 'pending', supplier_id INTEGER,
            branch_id INTEGER DEFAULT 1, source_module TEXT,
            source_id INTEGER, source_folio TEXT,
            financial_document_id INTEGER, treasury_movement_id INTEGER,
            journal_entry_id INTEGER,
            metadata_json TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def _make_services(conn):
    from core.services.finance.journal_entry_service import JournalEntryService
    from core.services.finance.financial_document_service import FinancialDocumentService
    from core.services.finance.treasury_movement_service import TreasuryMovementService
    from core.services.finance.operating_supplies_service import OperatingSuppliesService

    je = JournalEntryService(db=conn, gl_service=None)
    fd = FinancialDocumentService(db=conn)
    tm = TreasuryMovementService(db=conn, treasury_service=None)
    os_svc = OperatingSuppliesService(db=conn, journal_service=je,
                                      document_service=fd, treasury_service=tm)
    return os_svc


class TestOperatingSuppliesService(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.os_svc = _make_services(self.conn)

    def test_register_supply_contado_creates_treasury_and_journal(self):
        result = self.os_svc.register_supply_purchase(
            operation_id="sup-001",
            supply_type="thermal_rolls",
            total_amount=350.0,
            quantity=5.0,
            payment_method="efectivo",
        )
        self.assertTrue(result["supply_id"])
        self.assertTrue(result["movement_id"])  # UUIDv7
        self.assertTrue(result["journal_id"])  # UUIDv7
        tm_row = self.conn.execute(
            "SELECT movement_type FROM treasury_movements WHERE operation_id='sup-001-TM'"
        ).fetchone()
        self.assertIsNotNone(tm_row)
        self.assertEqual(tm_row["movement_type"], "outflow")
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account FROM journal_entries WHERE operation_id='sup-001-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["debit_account"], "630-papeleria_expense")
        self.assertEqual(je_row["credit_account"], "110-caja")
        supply_row = self.conn.execute(
            "SELECT status FROM operating_supplies WHERE operation_id='sup-001'"
        ).fetchone()
        self.assertEqual(supply_row["status"], "paid")

    def test_register_supply_credito_creates_document_and_journal(self):
        result = self.os_svc.register_supply_purchase(
            operation_id="sup-002",
            supply_type="cleaning",
            total_amount=600.0,
            payment_method=None,
            supplier_id=55,
        )
        self.assertTrue(result["supply_id"])
        self.assertTrue(result["document_id"])  # UUIDv7
        self.assertEqual(result["movement_id"], 0)
        fd_row = self.conn.execute(
            "SELECT document_type FROM financial_documents WHERE operation_id='sup-002-FD'"
        ).fetchone()
        self.assertIsNotNone(fd_row)
        self.assertEqual(fd_row["document_type"], "payable")
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account FROM journal_entries WHERE operation_id='sup-002-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["debit_account"], "625-limpieza_expense")
        self.assertEqual(je_row["credit_account"], "210-cuentas_por_pagar")

    def test_register_supply_idempotent(self):
        kwargs = dict(
            operation_id="sup-003",
            supply_type="bags",
            total_amount=200.0,
            payment_method="efectivo",
        )
        r1 = self.os_svc.register_supply_purchase(**kwargs)
        r2 = self.os_svc.register_supply_purchase(**kwargs)
        self.assertEqual(r1["supply_id"], r2["supply_id"])
        count = self.conn.execute(
            "SELECT COUNT(*) FROM operating_supplies WHERE operation_id='sup-003'"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_pay_supply_updates_status(self):
        result = self.os_svc.register_supply_purchase(
            operation_id="sup-004",
            supply_type="stationery",
            total_amount=150.0,
            payment_method=None,
        )
        supply_id = result["supply_id"]
        pay_result = self.os_svc.pay_supply_purchase(
            supply_id=supply_id, amount=150.0, payment_method="efectivo"
        )
        self.assertEqual(pay_result["nuevo_status"], "paid")
        row = self.conn.execute(
            "SELECT status FROM operating_supplies WHERE id=?", (supply_id,)
        ).fetchone()
        self.assertEqual(row["status"], "paid")

    def test_classify_supply_returns_correct_account(self):
        from core.services.finance.operating_supplies_service import OperatingSuppliesService
        self.assertEqual(
            OperatingSuppliesService.classify_supply("thermal_rolls"),
            "630-papeleria_expense"
        )
        self.assertEqual(
            OperatingSuppliesService.classify_supply("cleaning"),
            "625-limpieza_expense"
        )
        self.assertEqual(
            OperatingSuppliesService.classify_supply("bags"),
            "615-empaque_expense"
        )
        self.assertEqual(
            OperatingSuppliesService.classify_supply("uniforms"),
            "640-uniformes_expense"
        )
        self.assertEqual(
            OperatingSuppliesService.classify_supply("unknown_type"),
            "690-otros_gastos"
        )


if __name__ == "__main__":
    unittest.main()
