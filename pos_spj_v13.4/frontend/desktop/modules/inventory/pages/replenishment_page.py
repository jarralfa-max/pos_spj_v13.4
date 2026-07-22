"""Replenishment page (INV-25) — open suggestions + generate action.

UI only: the table and the generate button delegate to the presenter, which owns
the backend calls. Purchase-vs-transfer and urgency are shown in Spanish.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_primary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class ReplenishmentPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("replenishmentPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Reposición",
            subtitle="Sugerencias de compra y transferencia por reglas mín/máx.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.generate_button = create_primary_button(text="Generar sugerencias")
        self.generate_button.clicked.connect(self._on_generate)
        actions.addWidget(self.generate_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Disponible", "numeric"),
            ColumnSpec("Sugerido", "numeric"),
            ColumnSpec("Fuente", "text"),
            ColumnSpec("Urgencia", "status"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.open_suggestions()
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _on_generate(self) -> None:
        ok, message, _ = self._presenter.generate_suggestions()
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Reposición", message)
        if ok:
            self.refresh()
