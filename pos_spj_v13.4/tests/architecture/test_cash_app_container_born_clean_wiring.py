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
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        resolver = (
            ROOT / "backend/infrastructure/desktop/cash_operational_context.py"
        ).read_text(encoding="utf-8")
        self.assertIn("DesktopCashOperationalContextResolver", factory)
        self.assertNotIn("def _first_active_cash_device", factory)
        self.assertIn("_first_active_cash_device", resolver)
        self.assertIn("cash_registers", resolver)
        self.assertIn("cash_drawers", resolver)
        self.assertIn("pos_terminals", resolver)
        self.assertIn("status='ACTIVE'", resolver)


if __name__ == "__main__":
    unittest.main()
