from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashAppContainerBornCleanWiringTests(unittest.TestCase):
    def test_cash_limit_policy_uses_effective_dates_not_legacy_active_flag(self):
        source = (ROOT / "core/app_container.py").read_text(encoding="utf-8")
        cash_block = source[
            source.index("# FASE 7.7"):source.index("# CustomerCreditService")
        ]
        self.assertIn("cash_operation_limits", cash_block)
        self.assertIn("effective_from", cash_block)
        self.assertIn("effective_to", cash_block)
        self.assertNotIn("active=1", cash_block)

    def test_cash_factory_resolves_active_context_from_canonical_devices(self):
        source = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_first_active_cash_device", source)
        self.assertIn("cash_registers", source)
        self.assertIn("cash_drawers", source)
        self.assertIn("pos_terminals", source)
        self.assertIn("status='ACTIVE'", source)


if __name__ == "__main__":
    unittest.main()
