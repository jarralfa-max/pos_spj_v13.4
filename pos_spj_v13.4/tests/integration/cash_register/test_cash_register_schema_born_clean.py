import importlib
import sqlite3
import unittest

from backend.shared.ids import new_uuid


MIGRATION = "migrations.standalone.175_cash_register_bounded_context_schema"


class CashRegisterSchemaBornCleanTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.migration = importlib.import_module(MIGRATION)
        self.migration.run(self.db)

    def tearDown(self):
        self.db.close()

    def test_bootstrap_creates_only_canonical_cash_register_tables(self):
        tables = {row[0] for row in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {
            "cash_registers", "cash_drawers", "pos_terminals", "cash_shifts",
            "cash_ledger_entries", "cash_counts", "cash_count_denominations",
            "cash_cuts", "cash_differences", "cash_handovers",
            "cash_authorization_grants", "cash_audit_log", "cash_domain_events",
            "cash_outbox", "cash_processed_operations",
        }
        self.assertTrue(expected <= tables)
        self.assertTrue({"turno_actual", "movimientos_caja", "cierres_caja"}.isdisjoint(tables))

    def test_ids_and_money_are_text_and_no_autoincrement_exists(self):
        sql = "\n".join(row[0] or "" for row in self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name LIKE 'cash_%'"))
        self.assertNotIn("AUTOINCREMENT", sql.upper())
        self.assertNotIn(" REAL", sql.upper())
        for table in ("cash_shifts", "cash_ledger_entries", "cash_counts", "cash_cuts",
                      "cash_differences", "cash_handovers", "cash_domain_events", "cash_outbox"):
            columns = {row[1]: row[2].upper() for row in self.db.execute(f"PRAGMA table_info({table})")}
            self.assertEqual(columns["id"], "TEXT")

    def test_uuid_state_fk_and_positive_money_constraints_are_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO cash_registers(id,branch_id,name,status,created_at,updated_at) VALUES('1',?,?,?, ?,?)",
                            (new_uuid(), "Caja", "ACTIVE", "now", "now"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO cash_registers(id,branch_id,name,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                            (new_uuid(), new_uuid(), "Caja", "UNKNOWN", "now", "now"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO cash_ledger_entries(id,shift_id,branch_id,movement_type,direction,amount,operation_id,recorded_by,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            (new_uuid(), new_uuid(), new_uuid(), "CASH_SALE", "INFLOW", "-1", new_uuid(), new_uuid(), "now"))

    def test_active_shift_final_z_cut_and_operation_idempotency_are_unique(self):
        index_sql = "\n".join(row[0] or "" for row in self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name LIKE 'cash_%'"))
        self.assertIn("CASH_SHIFTS", index_sql.upper())
        self.assertIn("CASH_CUTS", index_sql.upper())
        self.assertIn("WHERE", index_sql.upper())
        self.assertIn("OPERATION_ID", index_sql.upper())

    def test_bootstrap_is_repeatable_and_foreign_keys_are_clean(self):
        self.migration.run(self.db)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
