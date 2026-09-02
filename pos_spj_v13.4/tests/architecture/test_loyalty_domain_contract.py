"""LOY-2 structural guardrails for the canonical Loyalty domain. Mirrors
tests/architecture/test_sales_domain_contract.py exactly."""
import ast
from decimal import Decimal
from pathlib import Path
import unittest

from backend.domain.loyalty.events import ALL_LOYALTY_EVENTS, FINANCE_ALIGNED_EVENTS
from backend.shared.events.event_names import EventName

REPO = Path(__file__).resolve().parents[2]
DOMAIN = REPO / "backend" / "domain" / "loyalty"


class LoyaltyDomainArchitectureTests(unittest.TestCase):
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

    def test_event_catalog_covers_master_prompt_62(self):
        expected = {
            "LOYALTY_PROGRAM_CREATED", "LOYALTY_MEMBERSHIP_ENROLLED",
            "LOYALTY_POINTS_ISSUED", "LOYALTY_POINTS_RESERVED",
            "LOYALTY_POINTS_REDEEMED", "LOYALTY_POINTS_RELEASED",
            "LOYALTY_POINTS_EXPIRED", "LOYALTY_TRANSACTION_REVERSED",
        }
        self.assertTrue(expected <= ALL_LOYALTY_EVENTS)
        # Legacy bus names must never leak into the new catalog.
        self.assertNotIn("LOYALTY_POINTS_EARNED", ALL_LOYALTY_EVENTS)

    def test_finance_aligned_events_are_real_event_name_members(self):
        """The 4 events LOY-2 deliberately reuses verbatim from Finance's
        already-built handlers must actually exist as EventName members with
        the identical string value — guards against the two vocabularies
        silently drifting apart in a future edit to either file."""
        event_name_values = {member.value for member in EventName}
        for event in FINANCE_ALIGNED_EVENTS:
            self.assertIn(event, event_name_values,
                           f"{event} no longer matches an EventName member")

    def test_domain_exposes_core_entities(self):
        for module, class_name in (
            ("entities/loyalty_program.py", "class LoyaltyProgram"),
            ("entities/loyalty_account.py", "class LoyaltyAccount"),
            ("entities/loyalty_membership.py", "class LoyaltyMembership"),
            ("entities/loyalty_transaction.py", "class LoyaltyTransaction"),
        ):
            source = (DOMAIN / module).read_text(encoding="utf-8")
            self.assertIn(class_name, source)

    def test_balance_policy_is_the_only_balance_assembler(self):
        """No other file under backend/domain/loyalty/ may compute a balance
        by summing points_amount directly — every caller must go through
        LoyaltyBalancePolicy (master prompt §11: single source of truth)."""
        allowed = {
            DOMAIN / "policies" / "balance_policy.py",
        }
        offenders = []
        for path in DOMAIN.rglob("*.py"):
            if path in allowed or path.name.startswith("test_"):
                continue
            source = path.read_text(encoding="utf-8")
            if "points_amount for t in" in source or "sum(t.points_amount" in source:
                offenders.append(str(path.relative_to(REPO)))
        self.assertFalse(offenders, offenders)

    def test_transaction_amounts_use_decimal_only(self):
        source = (DOMAIN / "entities" / "loyalty_transaction.py").read_text(encoding="utf-8")
        self.assertIn("from decimal import Decimal", source)
        self.assertNotIn(": float", source)


if __name__ == "__main__":
    unittest.main()
