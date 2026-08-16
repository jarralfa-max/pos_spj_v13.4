from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashOperationalContextResolverArchitectureTests(unittest.TestCase):
    def test_factory_delegates_active_context_to_explicit_resolver(self):
        factory = (ROOT / "backend/infrastructure/desktop/cash_register_factory.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("DesktopCashOperationalContextResolver", factory)
        self.assertIn("operational_context.context().as_presenter_dict()", factory)
        self.assertIn("operational_context.active_shift_id", factory)
        self.assertIn("operational_context.active_count_context", factory)
        self.assertNotIn("def _first_active_cash_device", factory)
        self.assertNotIn("def _current_active_cash_shift", factory)

    def test_resolver_uses_canonical_tables_and_never_fabricates_context(self):
        source = (
            ROOT / "backend/infrastructure/desktop/cash_operational_context.py"
        ).read_text(encoding="utf-8")
        for required in (
            "class CashOperationalContext",
            "class DesktopCashOperationalContextResolver",
            "cash_registers",
            "cash_drawers",
            "pos_terminals",
            "cash_shifts",
            "CashShiftLifecyclePolicy.ACTIVE_STATUSES",
        ):
            self.assertIn(required, source)
        for forbidden in (
            '"admin"',
            '"desktop"',
            '"system"',
            '"MAIN"',
            '"1"',
            "uuid.uuid4",
            "new_uuid",
            "active_cash_register_id or \"",
            "active_cash_shift_id or \"",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
