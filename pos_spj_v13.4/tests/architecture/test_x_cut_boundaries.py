from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class XCutBoundaryTests(unittest.TestCase):
    def test_x_cut_use_case_uses_print_port_and_never_closes_shift(self):
        source = (ROOT / "backend/application/cash_register/x_cut_use_cases.py").read_text(encoding="utf-8")
        self.assertIn("class XCutPrintGateway(Protocol)", source)
        self.assertNotIn("set_lifecycle", source)
        self.assertNotIn("QPrinter", source)

    def test_sensitive_visibility_is_permission_guarded(self):
        source = (ROOT / "backend/application/cash_register/x_cut_query_service.py").read_text(encoding="utf-8")
        self.assertIn("X_CUT_VIEW", source)
        self.assertIn("VIEW_SENSITIVE_AMOUNTS", source)


if __name__ == "__main__": unittest.main()
