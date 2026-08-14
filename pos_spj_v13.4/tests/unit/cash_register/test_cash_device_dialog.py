import os
import unittest
from dataclasses import dataclass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5.QtWidgets import QApplication
    from frontend.desktop.modules.cash_register.cash_register_dialogs import CashDeviceDialog
except Exception:  # pragma: no cover - optional UI dependency
    QApplication = None
    CashDeviceDialog = None


@dataclass(frozen=True)
class _RegisterRow:
    id: str
    name: str
    branch_name: str


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class CashDeviceDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_drawer_dialog_shows_register_name_but_returns_internal_uuid(self):
        register_id = "019ff99a-ccc2-7529-b3b6-8736303cc870"
        dialog = CashDeviceDialog(
            kind="drawer",
            registers=(_RegisterRow(register_id, "Caja mostrador", "Principal"),),
        )
        dialog.name.setText("Cajón A")
        dialog.register.setCurrentIndex(1)

        result = dialog.result_value()

        self.assertIn("Caja mostrador", dialog.register.currentText())
        self.assertIn("Principal", dialog.register.currentText())
        self.assertEqual(result.name, "Cajón A")
        self.assertEqual(result.register_id, register_id)


if __name__ == "__main__":
    unittest.main()
