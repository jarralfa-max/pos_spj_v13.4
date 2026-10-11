"""Diálogo de consulta de perfil contable de instrumentos (solo lectura).

La administración completa de perfiles exige el permiso
``finance.commercial_posting_profile.manage`` y no reexpresa asientos pasados.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialogButtonBox

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class CommercialPostingProfileDialog(StandardDialog):
    def __init__(self, parent, profile_rows: list[list[str]]) -> None:
        super().__init__(parent, title="Perfil contable", width=560)
        self.setMinimumSize(560, 320)
        layout = self.content_layout()
        table = StandardTable([ColumnSpec("Rol contable"), ColumnSpec("Cuenta", "date")], self)
        table.load_rows(profile_rows)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText("Cerrar")
        buttons.clicked.connect(lambda _b: self.accept())
        self.add_footer_widget(buttons)
