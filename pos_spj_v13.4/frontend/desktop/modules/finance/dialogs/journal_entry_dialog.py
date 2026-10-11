"""Diálogo informativo de asiento (detalle de líneas)."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialogButtonBox

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class JournalEntryDialog(StandardDialog):
    """Solo lectura: muestra las líneas debe/haber de un asiento."""

    def __init__(self, parent, lines_model) -> None:
        super().__init__(parent, title="Detalle del asiento", width=640)
        self.setMinimumSize(640, 360)
        layout = self.content_layout()
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
        buttons.button(QDialogButtonBox.Close).setText("Cerrar")
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(lambda _b: self.accept())
        self.add_footer_widget(buttons)
