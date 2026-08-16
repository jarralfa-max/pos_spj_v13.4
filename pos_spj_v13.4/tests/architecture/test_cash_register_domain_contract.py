"""CASH-2 structural guardrails for the canonical domain."""
import ast
from pathlib import Path
import unittest

from backend.domain.cash_register.events import ALL_CASH_EVENTS


REPO = Path(__file__).resolve().parents[2]
DOMAIN = REPO / "backend" / "domain" / "cash_register"


class CashRegisterDomainArchitectureTests(unittest.TestCase):
    def test_domain_has_no_io_ui_or_float_literals(self):
        offenders = []
        forbidden_imports = ("sqlite3", "PyQt", "repositories", "infrastructure.db")
        for path in DOMAIN.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                             else [node.module or ""])
                    if any(any(token in name for token in forbidden_imports) for name in names):
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: import")
                if isinstance(node, ast.Constant) and isinstance(node.value, float):
                    offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: float")
        self.assertFalse(offenders, "\n".join(offenders))

    def test_event_catalog_covers_cash_2_aggregates(self):
        expected = {
            "CASH_REGISTER_CREATED", "CASH_DRAWER_ASSIGNED", "CASH_TERMINAL_ASSIGNED",
            "CASH_SHIFT_OPENED", "CASH_MOVEMENT_RECORDED", "CASH_BLIND_COUNT_CONFIRMED",
            "CASH_X_CUT_GENERATED", "CASH_Z_CUT_GENERATED", "CASH_DIFFERENCE_DETECTED",
            "CASH_HANDOVER_RECEIVED", "CASH_DEPOSIT_PREPARED",
            "CASH_REFUND_EXECUTED", "CASH_DRAWER_OPENED", "CASH_SHIFT_FORCE_CLOSED",
        }
        self.assertTrue(expected <= ALL_CASH_EVENTS)
        self.assertNotIn("CAJA_CERRADA", ALL_CASH_EVENTS)
        self.assertNotIn("CASH_DEPOSIT_CONFIRMED", ALL_CASH_EVENTS)

    def test_domain_exposes_cash_2_ownership_entities(self):
        source = (DOMAIN / "entities.py").read_text(encoding="utf-8")
        for required in (
            "class CashRegister",
            "class CashDrawer",
            "class PosTerminal",
            "class CashShift",
            "class CashLedgerEntry",
            "class CashLedger",
            "class BlindCashCount",
            "class XCut",
            "class ZCut",
            "class CashDifference",
            "class CashHandover",
            "class PaymentRecord",
            "class PaymentAllocation",
            "class CashRefundExecution",
            "class DrawerOpenEvent",
        ):
            self.assertIn(required, source)

    def test_shift_lifecycle_policy_is_used_by_domain_and_application(self):
        policy = (DOMAIN / "policies" / "workflow_policies.py").read_text(encoding="utf-8")
        entities = (DOMAIN / "entities.py").read_text(encoding="utf-8")
        use_case = (
            REPO / "backend" / "application" / "cash_register" / "shift_use_cases.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class CashShiftLifecyclePolicy", policy)
        self.assertIn("TRANSITIONS", policy)
        self.assertIn("ACTIVE_STATUSES", policy)
        self.assertIn("CashShiftLifecyclePolicy.ensure_transition", entities)
        self.assertIn("CashShiftLifecyclePolicy.ensure_transition", use_case)


if __name__ == "__main__":
    unittest.main()

