import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CashHardwareBoundaryTest(unittest.TestCase):
    def test_vendor_protocols_are_confined_to_infrastructure(self):
        for relative in ("backend/domain/cash_register", "backend/application/cash_register", "frontend"):
            for path in (ROOT / relative).rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("import serial", source, path)
                self.assertNotIn("import usb", source, path)
                self.assertNotIn("import escpos", source, path)

    def test_hardware_use_cases_do_not_import_vendor_drivers(self):
        path = ROOT / "backend/application/cash_register/hardware_use_cases.py"
        imports = [node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                   if isinstance(node, (ast.Import, ast.ImportFrom))]
        rendered = "\n".join(ast.unparse(node) for node in imports)
        self.assertNotIn("infrastructure.hardware", rendered)

    def test_hardware_failures_are_alerted_through_outbox(self):
        source = (ROOT / "backend/application/cash_register/hardware_use_cases.py").read_text(encoding="utf-8")
        self.assertIn("alert_required=True", source)
        self.assertNotIn("whatsapp", source.lower())


if __name__ == "__main__": unittest.main()
