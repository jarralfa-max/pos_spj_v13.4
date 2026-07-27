"""Diálogo informativo de asiento (detalle de líneas)."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

from frontend.desktop.components.tables import ColumnSpec, StandardTable


class JournalEntryDialog(QDialog):
    """Solo lectura: muestra las líneas debe/haber de un asiento."""

    def __init__(self, parent, lines_model) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self.setWindowTitle("Detalle del asiento")
        self.setMinimumSize(640, 360)
        layout = QVBoxLayout(self)
        table = StandardTable([
            ColumnSpec("Cuenta", "date"),
            ColumnSpec("Nombre"),
            ColumnSpec("Descripción"),
            ColumnSpec("Debe", "numeric"),
            ColumnSpec("Haber", "numeric"),
        ], self)
        table.load_rows(lines_model.rows)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(lambda _b: self.accept())
        layout.addWidget(buttons)
