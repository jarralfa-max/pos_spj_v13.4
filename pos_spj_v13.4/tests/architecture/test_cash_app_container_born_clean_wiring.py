from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashAppContainerBornCleanWiringTests(unittest.TestCase):
    def test_cash_limit_policy_uses_effective_dates_not_legacy_active_flag(self):
        # `core/app_container.py` ya no existe: el tope se resuelve en el repositorio.
        cash_block = (
            ROOT / "backend/infrastructure/db/repositories/cash_register/operation_limits.py"
        ).read_text(encoding="utf-8")
        self.assertIn("cash_operation_limits", cash_block)
        self.assertIn("effective_from", cash_block)
        self.assertIn("effective_to", cash_block)
        self.assertNotIn("active=1", cash_block)

    def test_cash_limits_resolve_per_operation_not_at_screen_construction(self):
        # Re-auditoría 2026-10-07: el tope se leía al abrir Caja; uno capturado
        # después no aplicaba hasta reabrir el módulo.
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        self.assertIn("EffectiveCashLimitPolicy(connection, operation_type)", factory)
        self.assertNotIn("alert_threshold=safe_drop_limit.approval_threshold", factory)

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
