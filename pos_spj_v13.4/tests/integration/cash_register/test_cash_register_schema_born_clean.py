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
            "cash_shift_assignments", "cash_ledger_entries", "payment_records",
            "payment_allocations", "cash_counts", "cash_count_denominations",
            "cash_cuts", "cash_differences", "cash_handovers",
            "cash_deposit_preparations", "cash_authorization_grants",
            "cash_refund_executions", "drawer_open_events", "cash_audit_log",
            "cash_domain_events", "cash_outbox", "cash_processed_operations",
        }
        self.assertTrue(expected <= tables)
        self.assertTrue({"turno_actual", "movimientos_caja", "cierres_caja"}.isdisjoint(tables))

    def test_ids_and_money_are_text_and_no_autoincrement_exists(self):
        sql = "\n".join(row[0] or "" for row in self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name LIKE 'cash_%'"))
        self.assertNotIn("AUTOINCREMENT", sql.upper())
        self.assertNotIn(" REAL", sql.upper())
        for table in ("cash_shifts", "cash_shift_assignments", "cash_ledger_entries",
                      "payment_records", "payment_allocations", "cash_counts", "cash_cuts",
                      "cash_differences", "cash_handovers", "cash_deposit_preparations",
                      "cash_refund_executions", "drawer_open_events",
                      "cash_domain_events", "cash_outbox"):
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
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(cash_shifts)")}
        self.assertIn("business_date", columns)

    def test_domain_catalog_constraints_match_cash_domain_model(self):
        register_id, drawer_id, terminal_id = self._seed_shift_dependencies()
        self.db.execute(
            "UPDATE cash_registers SET status='MAINTENANCE' WHERE id=?",
            (register_id,),
        )
        self.db.execute(
            "UPDATE cash_drawers SET status='RETIRED' WHERE id=?",
            (drawer_id,),
        )
        self.db.execute(
            "UPDATE pos_terminals SET status='BLOCKED' WHERE id=?",
            (terminal_id,),
        )
        shift_id = self._seed_shift(register_id, drawer_id, terminal_id, status="PENDING_REVIEW")
        self.db.execute(
            "INSERT INTO cash_ledger_entries(id,shift_id,branch_id,movement_type,direction,amount,operation_id,recorded_by,concept,recorded_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), shift_id, self.branch_id, "CASH_PICKUP", "OUTFLOW", "1.00", new_uuid(), self.cashier_id, "pickup", "now"),
        )

    def test_active_shift_final_z_cut_and_operation_idempotency_are_unique(self):
        index_sql = "\n".join(row[0] or "" for row in self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name LIKE 'cash_%'"))
        self.assertIn("CASH_SHIFTS", index_sql.upper())
        self.assertIn("CASH_CUTS", index_sql.upper())
        self.assertIn("WHERE", index_sql.upper())
        self.assertIn("OPERATION_ID", index_sql.upper())

    def test_settlement_refund_drawer_and_deposit_constraints_are_enforced(self):
        register_id, drawer_id, terminal_id = self._seed_shift_dependencies()
        shift_id = self._seed_shift(register_id, drawer_id, terminal_id)
        payment_id = new_uuid()
        self.db.execute(
            "INSERT INTO payment_records(id,sale_id,shift_id,branch_id,amount_to_settle,operation_id,recorded_by,recorded_at,status) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (payment_id, new_uuid(), shift_id, self.branch_id, "100.00", new_uuid(), self.cashier_id, "now", "CONFIRMED"),
        )
        self.db.execute(
            "INSERT INTO payment_allocations(id,payment_record_id,method_type,amount,affects_drawer,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (new_uuid(), payment_id, "BANK_CARD", "50.00", 0, "now"),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO payment_allocations(id,payment_record_id,method_type,amount,affects_drawer,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (new_uuid(), payment_id, "BANK_CARD", "1.00", 1, "now"),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO drawer_open_events(id,drawer_id,shift_id,branch_id,opened_by,reason,operation_id,opened_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (new_uuid(), drawer_id, shift_id, self.branch_id, self.cashier_id, "NO_REASON", new_uuid(), "now"),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO cash_refund_executions(id,refund_id,sale_id,shift_id,branch_id,method,amount,executed_by,authorized_by,operation_id,executed_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (new_uuid(), new_uuid(), new_uuid(), shift_id, self.branch_id, "CASH", "10.00", self.cashier_id, self.cashier_id, new_uuid(), "now"),
            )

    def test_bootstrap_is_repeatable_and_foreign_keys_are_clean(self):
        self.migration.run(self.db)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def _seed_shift_dependencies(self):
        self.branch_id = new_uuid()
        self.cashier_id = new_uuid()
        register_id = new_uuid()
        drawer_id = new_uuid()
        terminal_id = new_uuid()
        self.db.execute(
            "INSERT INTO cash_registers(id,branch_id,name,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (register_id, self.branch_id, "Caja 1", "ACTIVE", "now", "now"),
        )
        self.db.execute(
            "INSERT INTO cash_drawers(id,branch_id,register_id,name,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (drawer_id, self.branch_id, register_id, "Cajón 1", "ACTIVE", "now", "now"),
        )
        self.db.execute(
            "INSERT INTO pos_terminals(id,branch_id,register_id,name,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (terminal_id, self.branch_id, register_id, "Terminal 1", "ACTIVE", "now", "now"),
        )
        return register_id, drawer_id, terminal_id

    def _seed_shift(self, register_id, drawer_id, terminal_id, *, status="OPEN"):
        shift_id = new_uuid()
        self.db.execute(
            "INSERT INTO cash_shifts(id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,opening_amount,opening_operation_id,status,opened_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (shift_id, self.branch_id, register_id, drawer_id, terminal_id, self.cashier_id, "100.00", new_uuid(), status, "now"),
        )
        return shift_id


if __name__ == "__main__":
    unittest.main()
