# tests/finance/test_financial_trace_maintenance.py — SPJ ERP v13.4
"""Tests for MaintenanceFinanceService."""
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
        CREATE TABLE IF NOT EXISTS maintenance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT UNIQUE NOT NULL,
            asset_id INTEGER, maintenance_type TEXT, description TEXT,
            amount REAL, status TEXT DEFAULT 'pending',
            supplier_id INTEGER, branch_id INTEGER DEFAULT 1,
            source_module TEXT, source_id INTEGER, source_folio TEXT,
            financial_document_id INTEGER, treasury_movement_id INTEGER,
            journal_entry_id INTEGER, capitalizable INTEGER DEFAULT 0,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
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
    """)
    return conn


def _make_services(conn):
    from core.services.finance.journal_entry_service import JournalEntryService
    from core.services.finance.financial_document_service import FinancialDocumentService
    from core.services.finance.treasury_movement_service import TreasuryMovementService
    from core.services.finance.maintenance_finance_service import MaintenanceFinanceService

    je = JournalEntryService(db=conn, gl_service=None)
    fd = FinancialDocumentService(db=conn)
    tm = TreasuryMovementService(db=conn, treasury_service=None)
    mnt = MaintenanceFinanceService(db=conn, journal_service=je,
                                    document_service=fd, treasury_service=tm)
    return mnt


class TestMaintenanceFinanceService(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.mnt = _make_services(self.conn)

    def test_register_maintenance_contado_creates_treasury_and_journal(self):
        result = self.mnt.register_maintenance(
            operation_id="mnt-001",
            amount=1500.0,
            maintenance_type="corrective",
            description="Reparacion bomba de agua",
            payment_method="efectivo",
        )
        self.assertGreater(result["maintenance_id"], 0)
        self.assertGreater(result["movement_id"], 0)
        self.assertGreater(result["journal_id"], 0)
        tm_row = self.conn.execute(
            "SELECT movement_type FROM treasury_movements WHERE operation_id='mnt-001-TM'"
        ).fetchone()
        self.assertIsNotNone(tm_row)
        self.assertEqual(tm_row["movement_type"], "outflow")
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account FROM journal_entries WHERE operation_id='mnt-001-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["debit_account"], "620-mantenimiento_expense")
        self.assertEqual(je_row["credit_account"], "110-caja")

    def test_register_maintenance_credito_creates_document_and_journal(self):
        result = self.mnt.register_maintenance(
            operation_id="mnt-002",
            amount=4000.0,
            maintenance_type="preventive",
            description="Servicio anual HVAC",
            payment_method=None,
            supplier_id=99,
        )
        self.assertGreater(result["maintenance_id"], 0)
        self.assertGreater(result["document_id"], 0)
        self.assertEqual(result["movement_id"], 0)
        fd_row = self.conn.execute(
            "SELECT document_type FROM financial_documents WHERE operation_id='mnt-002-FD'"
        ).fetchone()
        self.assertIsNotNone(fd_row)
        self.assertEqual(fd_row["document_type"], "payable")
        je_row = self.conn.execute(
            "SELECT credit_account FROM journal_entries WHERE operation_id='mnt-002-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["credit_account"], "210-cuentas_por_pagar")

    def test_register_maintenance_capitalizable_uses_asset_account(self):
        result = self.mnt.register_maintenance(
            operation_id="mnt-003",
            amount=20000.0,
            maintenance_type="repair",
            description="Mejora estructural techo",
            payment_method="transferencia",
            is_capitalizable=True,
        )
        self.assertGreater(result["maintenance_id"], 0)
        je_row = self.conn.execute(
            "SELECT debit_account, event_type FROM journal_entries WHERE operation_id='mnt-003-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["debit_account"], "150-activos_fijos")
        self.assertEqual(je_row["event_type"], "MAINTENANCE_CAPITALIZED")
        mnt_row = self.conn.execute(
            "SELECT capitalizable FROM maintenance_records WHERE operation_id='mnt-003'"
        ).fetchone()
        self.assertEqual(mnt_row["capitalizable"], 1)

    def test_register_maintenance_idempotent(self):
        kwargs = dict(
            operation_id="mnt-004",
            amount=800.0,
            maintenance_type="corrective",
            payment_method="efectivo",
        )
        r1 = self.mnt.register_maintenance(**kwargs)
        r2 = self.mnt.register_maintenance(**kwargs)
        self.assertEqual(r1["maintenance_id"], r2["maintenance_id"])
        count = self.conn.execute(
            "SELECT COUNT(*) FROM maintenance_records WHERE operation_id='mnt-004'"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_pay_maintenance_updates_status(self):
        result = self.mnt.register_maintenance(
            operation_id="mnt-005",
            amount=2500.0,
            maintenance_type="preventive",
            payment_method=None,
        )
        mnt_id = result["maintenance_id"]
        pay_result = self.mnt.pay_maintenance(mnt_id, amount=2500.0,
                                              payment_method="efectivo")
        self.assertEqual(pay_result["nuevo_status"], "paid")
        row = self.conn.execute(
            "SELECT status FROM maintenance_records WHERE id=?", (mnt_id,)
        ).fetchone()
        self.assertEqual(row["status"], "paid")

    def test_cancel_maintenance_updates_status(self):
        result = self.mnt.register_maintenance(
            operation_id="mnt-006",
            amount=600.0,
            maintenance_type="corrective",
            payment_method=None,
        )
        mnt_id = result["maintenance_id"]
        ok = self.mnt.cancel_maintenance(mnt_id)
        self.assertTrue(ok)
        row = self.conn.execute(
            "SELECT status FROM maintenance_records WHERE id=?", (mnt_id,)
        ).fetchone()
        self.assertEqual(row["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
