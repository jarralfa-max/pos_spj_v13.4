# tests/finance/test_financial_trace_assets.py — SPJ ERP v13.4
"""Tests for FixedAssetService."""
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
        CREATE TABLE IF NOT EXISTS fixed_assets (
            id TEXT PRIMARY KEY,
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
        CREATE TABLE IF NOT EXISTS asset_depreciation_entries (
            id TEXT PRIMARY KEY,
            operation_id TEXT UNIQUE NOT NULL,
            asset_id TEXT NOT NULL, period TEXT NOT NULL,
            amount REAL NOT NULL, journal_entry_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def _make_services(conn):
    from core.services.finance.journal_entry_service import JournalEntryService
    from core.services.finance.fixed_asset_service import FixedAssetService

    je = JournalEntryService(db=conn, gl_service=None)
    fa = FixedAssetService(db=conn, journal_service=je)
    return fa, je


class TestFixedAssetService(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.fa, self.je = _make_services(self.conn)

    def test_register_asset_creates_fixed_asset_row(self):
        asset_id = self.fa.register_asset_purchase(
            operation_id="asset-001",
            asset_name="Congelador Industrial",
            asset_type="equipment",
            acquisition_cost=25000.0,
            useful_life_months=60,
        )
        self.assertTrue(asset_id)
        row = self.conn.execute(
            "SELECT asset_name, acquisition_cost, status FROM fixed_assets WHERE id=?",
            (asset_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["asset_name"], "Congelador Industrial")
        self.assertAlmostEqual(row["acquisition_cost"], 25000.0)
        self.assertEqual(row["status"], "active")

    def test_register_asset_idempotent(self):
        id1 = self.fa.register_asset_purchase(
            operation_id="asset-002",
            asset_name="Laptop",
            asset_type="technology",
            acquisition_cost=18000.0,
        )
        id2 = self.fa.register_asset_purchase(
            operation_id="asset-002",
            asset_name="Laptop",
            asset_type="technology",
            acquisition_cost=18000.0,
        )
        self.assertEqual(id1, id2)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM fixed_assets WHERE operation_id='asset-002'"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_register_asset_creates_journal_entry(self):
        self.fa.register_asset_purchase(
            operation_id="asset-003",
            asset_name="Camion Repartidor",
            asset_type="vehicle",
            acquisition_cost=300000.0,
        )
        je_row = self.conn.execute(
            "SELECT debit_account, credit_account, event_type FROM journal_entries"
            " WHERE operation_id='asset-003-JE'"
        ).fetchone()
        self.assertIsNotNone(je_row)
        self.assertEqual(je_row["event_type"], "FIXED_ASSET_PURCHASED")
        self.assertEqual(je_row["debit_account"], "150-activos_fijos")

    def test_depreciate_asset_creates_entry(self):
        asset_id = self.fa.register_asset_purchase(
            operation_id="asset-004",
            asset_name="Refrigerador",
            asset_type="equipment",
            acquisition_cost=12000.0,
            useful_life_months=60,
        )
        dep_id = self.fa.depreciate_asset(asset_id=asset_id, period="2026-01")
        self.assertTrue(dep_id)
        dep_row = self.conn.execute(
            "SELECT amount, period FROM asset_depreciation_entries WHERE id=?",
            (dep_id,)
        ).fetchone()
        self.assertIsNotNone(dep_row)
        self.assertEqual(dep_row["period"], "2026-01")
        self.assertAlmostEqual(dep_row["amount"], 200.0)  # 12000/60

    def test_depreciate_asset_idempotent(self):
        asset_id = self.fa.register_asset_purchase(
            operation_id="asset-005",
            asset_name="Impresora",
            asset_type="equipment",
            acquisition_cost=6000.0,
            useful_life_months=36,
        )
        id1 = self.fa.depreciate_asset(asset_id=asset_id, period="2026-02")
        id2 = self.fa.depreciate_asset(asset_id=asset_id, period="2026-02")
        # Same period → idempotent, returns existing id
        self.assertEqual(id1, id2)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM asset_depreciation_entries"
            " WHERE asset_id=? AND period='2026-02'",
            (asset_id,)
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_depreciate_asset_updates_accumulated_depreciation(self):
        asset_id = self.fa.register_asset_purchase(
            operation_id="asset-006",
            asset_name="Mesa de trabajo",
            asset_type="furniture",
            acquisition_cost=3000.0,
            useful_life_months=60,
        )
        self.fa.depreciate_asset(asset_id=asset_id, period="2026-03", amount=50.0)
        row = self.conn.execute(
            "SELECT accumulated_depreciation, current_value FROM fixed_assets WHERE id=?",
            (asset_id,)
        ).fetchone()
        self.assertAlmostEqual(row["accumulated_depreciation"], 50.0)
        self.assertAlmostEqual(row["current_value"], 2950.0)

    def test_dispose_asset_updates_status(self):
        asset_id = self.fa.register_asset_purchase(
            operation_id="asset-007",
            asset_name="Bascula antigua",
            asset_type="equipment",
            acquisition_cost=2000.0,
        )
        ok = self.fa.dispose_asset(asset_id=asset_id, reason="sold")
        self.assertTrue(ok)
        row = self.conn.execute(
            "SELECT status FROM fixed_assets WHERE id=?", (asset_id,)
        ).fetchone()
        self.assertEqual(row["status"], "sold")


if __name__ == "__main__":
    unittest.main()
