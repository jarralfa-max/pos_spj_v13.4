"""SALES-5/POS-5: repositories cannot own transactions or schema. Mirrors
tests/architecture/test_cash_register_unit_of_work_boundary.py exactly."""
import ast
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "backend/infrastructure/db/repositories/sales"


class SalesUnitOfWorkArchitectureTests(unittest.TestCase):
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
        from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork

        source = (ROOT / "unit_of_work.py").read_text(encoding="utf-8")
        for attribute in ("sales", "outbox"):
            self.assertIn(f"self.{attribute} =", source)
        self.assertTrue(callable(SalesUnitOfWork.commit))
        self.assertTrue(callable(SalesUnitOfWork.rollback))
        self.assertTrue(hasattr(SalesUnitOfWork, "__enter__"))
        self.assertTrue(hasattr(SalesUnitOfWork, "__exit__"))


if __name__ == "__main__":
    unittest.main()
