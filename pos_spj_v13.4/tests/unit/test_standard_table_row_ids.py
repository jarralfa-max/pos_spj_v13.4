import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5.QtWidgets import QApplication
    from frontend.desktop.components.tables import ColumnSpec, StandardTable
except Exception:  # pragma: no cover - optional UI dependency
    QApplication = None
    ColumnSpec = None
    StandardTable = None


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class StandardTableRowIdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selected_row_id_is_preserved_from_any_selected_cell(self):
        row_id = "019ff99a-ccc2-7529-b3b6-8736303cc870"
        table = StandardTable([
            ColumnSpec("Nombre"),
            ColumnSpec("Estado"),
        ])
        table.load_rows([["kkkk", "ACTIVE"]], row_ids=[row_id])

        table.setCurrentCell(0, 1)

        self.assertEqual(table.selected_row_id(), row_id)


if __name__ == "__main__":
    unittest.main()
