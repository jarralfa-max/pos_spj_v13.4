"""Diálogo de sólo lectura con una tabla (detalle de asiento, checklist, etc.)."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialogButtonBox, QLabel

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class TableDialog(StandardDialog):
    def __init__(self, parent, title: str, columns: list[ColumnSpec], model, *,
                 note: str = "", width: int = 720) -> None:
        super().__init__(parent, title=title, width=width)
        self.setMinimumSize(width, 360)
        layout = self.content_layout()
        if note:
            label = QLabel(note, self)
            label.setWordWrap(True)
            label.setProperty("role", "muted")
            layout.addWidget(label)
        self.table = StandardTable(columns, self)
        self.table.load_rows(model.rows, row_ids=model.row_ids or None)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText("Cerrar")
        buttons.rejected.connect(self.reject)
        self.add_footer_widget(buttons)
