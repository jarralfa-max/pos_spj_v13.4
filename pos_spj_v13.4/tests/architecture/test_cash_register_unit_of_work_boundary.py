"""CASH-4: repositories cannot own transactions or schema."""
import ast
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "backend/infrastructure/db/repositories/cash_register"


class CashRegisterUnitOfWorkArchitectureTests(unittest.TestCase):
    def test_repositories_do_not_commit_rollback_or_change_schema(self):
        source = (ROOT / "repositories.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"commit", "rollback"}:
                    calls.append((node.lineno, node.func.attr))
        self.assertFalse(calls, str(calls))
        upper = source.upper()
        self.assertNotIn("CREATE TABLE", upper)
        self.assertNotIn("ALTER TABLE", upper)
        self.assertNotIn("DROP TABLE", upper)

    def test_uow_exposes_one_boundary_for_all_required_records(self):
        from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork

        source = (ROOT / "unit_of_work.py").read_text(encoding="utf-8")
        for attribute in ("shifts", "ledger", "counts", "cuts", "differences", "events", "outbox"):
            self.assertIn(f"self.{attribute} =", source)
        self.assertTrue(callable(CashRegisterUnitOfWork.commit))
        self.assertTrue(callable(CashRegisterUnitOfWork.rollback))


if __name__ == "__main__":
    unittest.main()

