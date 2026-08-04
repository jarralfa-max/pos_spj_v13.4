"""Settings page (INV-25 / §23) — inventory module parameters.

Presentation-only: lists the module's alerting policy (notification rules) —
event, scope, channel, minimum severity, throttle and active flag. All values
come from the presenter; no SQL, no business logic. Revisiting the section
re-reads the rules.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class SettingsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventorySettingsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Configuración",
            subtitle="Parámetros del módulo: reglas de notificación, umbrales y "
                     "políticas.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Evento", "text"),
            ColumnSpec("Ámbito", "text"),
            ColumnSpec("Canal", "text"),
            ColumnSpec("Severidad mínima", "status"),
            ColumnSpec("Throttle", "text"),
            ColumnSpec("Activa", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.settings()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
