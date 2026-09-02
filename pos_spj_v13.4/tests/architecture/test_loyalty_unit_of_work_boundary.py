"""LOY-4: Loyalty repositories cannot own transactions or schema. Mirrors
tests/architecture/test_sales_unit_of_work_boundary.py exactly."""
import ast
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "backend/infrastructure/db/repositories/loyalty"


class LoyaltyUnitOfWorkArchitectureTests(unittest.TestCase):
    def test_repositories_do_not_commit_rollback_or_change_schema(self):
        calls = []
        combined_upper = ""
        for path in ROOT.glob("*.py"):
            if path.name == "unit_of_work.py":
                continue  # the UoW itself is allowed to commit/rollback
            source = path.read_text(encoding="utf-8")
            combined_upper += source.upper()
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in {"commit", "rollback"}:
                        calls.append((str(path.relative_to(REPO)), node.lineno, node.func.attr))
        self.assertFalse(calls, str(calls))
        self.assertNotIn("CREATE TABLE", combined_upper)
        self.assertNotIn("ALTER TABLE", combined_upper)
        self.assertNotIn("DROP TABLE", combined_upper)

    def test_uow_exposes_one_boundary_for_all_required_repositories(self):
        from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork

        source = (ROOT / "unit_of_work.py").read_text(encoding="utf-8")
        for attribute in ("programs", "accounts", "memberships", "transactions", "outbox"):
            self.assertIn(f"self.{attribute} =", source)
        self.assertTrue(callable(LoyaltyUnitOfWork.commit))
        self.assertTrue(callable(LoyaltyUnitOfWork.rollback))
        self.assertTrue(hasattr(LoyaltyUnitOfWork, "__enter__"))
        self.assertTrue(hasattr(LoyaltyUnitOfWork, "__exit__"))

    def test_transaction_repository_never_updates_points_amount_on_conflict(self):
        """Locks in the repository's own documented guarantee: the
        ON CONFLICT clause for loyalty_transactions may only touch
        status/reversal_transaction_id, never points_amount/transaction_type/
        operation_id (ledger rows are append-only, §11)."""
        source = (ROOT / "transaction_repository.py").read_text(encoding="utf-8")
        conflict_clause = source.split("ON CONFLICT(id) DO UPDATE SET", 1)[1].split('"""', 1)[0]
        self.assertNotIn("points_amount=", conflict_clause)
        self.assertNotIn("transaction_type=", conflict_clause)
        self.assertNotIn("operation_id=", conflict_clause)
        self.assertIn("status=excluded.status", conflict_clause)


if __name__ == "__main__":
    unittest.main()
