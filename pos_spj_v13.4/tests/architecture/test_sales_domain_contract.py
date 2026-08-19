"""SALES-3 structural guardrails for the canonical domain. Mirrors
tests/architecture/test_cash_register_domain_contract.py exactly."""
import ast
from pathlib import Path
import unittest

from backend.domain.sales.events import ALL_SALE_EVENTS


REPO = Path(__file__).resolve().parents[2]
DOMAIN = REPO / "backend" / "domain" / "sales"


class SalesDomainArchitectureTests(unittest.TestCase):
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

    def test_event_catalog_covers_sale_lifecycle(self):
        expected = {
            "SALE_STARTED", "SALE_LINE_ADDED", "SALE_CUSTOMER_ASSIGNED",
            "SALE_DISCOUNT_APPLIED", "SALE_SUSPENDED", "SALE_RESUMED",
            "SALE_CHECKOUT_STARTED", "SALE_COMPLETED", "SALE_CANCELLED",
            "SALE_RETURNED", "SALE_REVERSED",
        }
        self.assertTrue(expected <= ALL_SALE_EVENTS)
        # Legacy Spanish/aliased event names must never leak into the new catalog.
        self.assertNotIn("VENTA_COMPLETADA", ALL_SALE_EVENTS)
        self.assertNotIn("VENTA_SUSPENDIDA", ALL_SALE_EVENTS)

    def test_domain_exposes_sale_aggregate_and_line(self):
        source = (DOMAIN / "entities.py").read_text(encoding="utf-8")
        for required in ("class Sale", "class SaleLine"):
            self.assertIn(required, source)

    def test_lifecycle_policy_is_used_by_the_aggregate(self):
        policy = (DOMAIN / "policies" / "lifecycle_policies.py").read_text(encoding="utf-8")
        entities = (DOMAIN / "entities.py").read_text(encoding="utf-8")
        self.assertIn("class SaleLifecyclePolicy", policy)
        self.assertIn("TRANSITIONS", policy)
        self.assertIn("SaleLifecyclePolicy.ensure_transition", entities)

    def test_sale_totals_service_is_the_only_totals_assembler(self):
        """No other file under backend/domain/sales/ may construct a
        SaleTotals directly except the service and its own value object
        module — every caller must go through SaleTotalsService.calculate()
        (master prompt §73: 'Una sola evaluación de precios')."""
        allowed = {
            DOMAIN / "services" / "sale_totals_service.py",
            DOMAIN / "value_objects" / "sale_totals.py",
        }
        offenders = []
        for path in DOMAIN.rglob("*.py"):
            if path in allowed:
                continue
            source = path.read_text(encoding="utf-8")
            if "SaleTotals(" in source:
                offenders.append(str(path.relative_to(REPO)))
        self.assertFalse(offenders, offenders)


if __name__ == "__main__":
    unittest.main()
