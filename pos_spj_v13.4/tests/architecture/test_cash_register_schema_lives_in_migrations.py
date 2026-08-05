"""CASH-3 ownership, bootstrap and no-legacy guardrails."""
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "migrations/standalone/175_cash_register_bounded_context_schema.py"


class CashRegisterSchemaArchitectureTests(unittest.TestCase):
    def test_schema_is_registered_for_clean_and_incremental_bootstrap(self):
        engine = (REPO / "migrations/engine.py").read_text(encoding="utf-8")
        base = (REPO / "migrations/m000_base_schema.py").read_text(encoding="utf-8")
        self.assertIn('"175",  "migrations.standalone.175_cash_register_bounded_context_schema"', engine)
        self.assertIn("_create_cash_register_bounded_context", base)
        self.assertIn("175_cash_register_bounded_context_schema", base)
        self.assertNotIn('_safe(conn, _create_caja,              "caja")', base)

    def test_migration_has_no_legacy_rescue_or_dual_write(self):
        source = MIGRATION.read_text(encoding="utf-8")
        upper = source.upper()
        for legacy in ("MOVIMIENTOS_CAJA", "TURNOS_CAJA", "CIERRES_CAJA", "TURNO_ACTUAL", "CAJA_OPERATIONS"):
            self.assertNotIn(legacy, upper)
        for forbidden in ("ALTER TABLE", "INSERT INTO", "SELECT ", "LEGACY_ID", "AUTOINCREMENT", "LASTROWID"):
            self.assertNotIn(forbidden, upper)


if __name__ == "__main__":
    unittest.main()
