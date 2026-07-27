"""Diálogo de consulta de perfil contable de instrumentos (solo lectura).

La administración completa de perfiles exige el permiso
``finance.commercial_posting_profile.manage`` y no reexpresa asientos pasados.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

from frontend.desktop.components.tables import ColumnSpec, StandardTable


class CommercialPostingProfileDialog(QDialog):
    def __init__(self, parent, profile_rows: list[list[str]]) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self.setWindowTitle("Perfil contable")
        self.setMinimumSize(560, 320)
        layout = QVBoxLayout(self)
        table = StandardTable([ColumnSpec("Rol contable"), ColumnSpec("Cuenta", "date")], self)
        table.load_rows(profile_rows)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.clicked.connect(lambda _b: self.accept())
        layout.addWidget(buttons)
