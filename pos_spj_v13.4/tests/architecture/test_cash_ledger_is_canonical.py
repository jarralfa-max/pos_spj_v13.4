from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class CashLedgerArchitectureTests(unittest.TestCase):
    def test_commands_do_not_depend_on_legacy_cash_or_finance(self):
        source = (ROOT / "backend/application/cash_register/ledger_use_cases.py").read_text(encoding="utf-8")
        self.assertNotIn("legacy", source.lower())
        self.assertNotIn("FinanceService", source)
        self.assertNotIn("UPDATE cash_ledger", source)

    def test_movement_contract_rejects_legacy_handover_alias(self):
        enums = (ROOT / "backend/domain/cash_register/enums.py").read_text(encoding="utf-8")
        schema = (ROOT / "migrations/standalone/175_cash_register_bounded_context_schema.py").read_text(encoding="utf-8")
        self.assertNotIn('HANDOVER = "HANDOVER"', enums)
        movement_check = schema.split("movement_type TEXT NOT NULL CHECK", 1)[1].split("direction TEXT", 1)[0]
        self.assertIn("'CASH_HANDOVER'", movement_check)
        self.assertNotIn("'HANDOVER'", movement_check)

    def test_ui_is_thin_and_uses_canonical_components(self):
        source = (ROOT / "frontend/desktop/modules/cash_register/cash_ledger_page.py").read_text(encoding="utf-8")
        for component in ("PageHeader", "KPIBar", "StandardTable"):
            self.assertIn(component, source)
        self.assertNotIn("SELECT ", source)
        self.assertNotIn("sqlite", source)


if __name__ == "__main__": unittest.main()
