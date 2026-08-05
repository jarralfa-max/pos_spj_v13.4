"""Stdlib smoke coverage so LOSS-3 remains verifiable without pytest."""

import importlib
import sqlite3
import unittest

from backend.domain.losses.enums import LossClassificationCode
from backend.shared.ids import is_uuidv7, new_uuid


class LossesSchemaSmokeTest(unittest.TestCase):
    def setUp(self):
        self.migration = importlib.import_module(
            "migrations.standalone.174_losses_bounded_context_schema")
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.migration.run(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_schema_is_idempotent_and_referentially_clean(self):
        self.migration.run(self.connection)

        tables = {row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({
            "loss_cases", "loss_lines", "loss_outbox",
            "loss_processed_operations", "loss_quality_assessments",
            "loss_quality_evidence", "loss_transfer_links", "loss_transfer_claims",
        } <= tables)
        rows = self.connection.execute(
            "SELECT id, code FROM loss_classifications").fetchall()
        self.assertEqual(len(rows), len(LossClassificationCode))
        self.assertTrue(all(is_uuidv7(row[0]) for row in rows))
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        recovery_columns = {row[1] for row in self.connection.execute(
            "PRAGMA table_info(loss_recoveries)")}
        self.assertTrue({"status", "target_product_id", "approved_by_user_id",
                         "approved_at", "approval_reason"} <= recovery_columns)

    def test_operation_and_event_idempotency_constraints(self):
        operation_id, entity_id = new_uuid(), new_uuid()
        self.connection.execute(
            "INSERT INTO loss_processed_operations VALUES (?,?,?,?,?)",
            (operation_id, "CREATE", entity_id, "{}", "now"),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO loss_processed_operations VALUES (?,?,?,?,?)",
                (operation_id, "CREATE", new_uuid(), "{}", "now"),
            )

        event_id = new_uuid()
        values = (new_uuid(), event_id, "LOSS_CASE_CREATED", entity_id, operation_id,
                  None, new_uuid(), "{}", "PENDING", 0, "now", None, None, None)
        self.connection.execute(
            "INSERT INTO loss_outbox VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO loss_outbox VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_uuid(), event_id, "LOSS_CASE_CREATED", new_uuid(), new_uuid(),
                 None, new_uuid(), "{}", "PENDING", 0, "now", None, None, None),
            )

    def test_internal_foreign_keys_reject_orphan_lines(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """INSERT INTO loss_lines(
                    id, loss_case_id, product_id, quantity, weight, unit,
                    unit_cost, gross_value, recoverable_value, net_loss_value, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (new_uuid(), new_uuid(), new_uuid(), "1", "0", "kg",
                 "0", "0", "0", "0", "now"),
            )

    def test_m000_bootstrap_includes_losses_schema(self):
        from migrations.m000_base_schema import up

        connection = sqlite3.connect(":memory:")
        up(connection)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"loss_cases", "loss_outbox", "loss_processed_operations"} <= tables)
        quality_targets = {row[2] for row in connection.execute(
            "PRAGMA foreign_key_list(loss_quality_assessments)")}
        self.assertIn("inventory_quarantine", quality_targets)
        self.assertIn("inventory_temperature_readings", quality_targets)
        transfer_targets = {row[2] for row in connection.execute(
            "PRAGMA foreign_key_list(loss_transfer_links)")}
        self.assertTrue({"stock_transfers", "transfer_differences",
                         "transfer_difference_resolutions", "transfer_receipts"}
                        <= transfer_targets)
        self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        connection.close()


if __name__ == "__main__":
    unittest.main()
