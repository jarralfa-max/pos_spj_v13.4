"""Alerts page (INV-25 / §23) — recent inventory alerts.

Presentation-only: lists recent alerts dispatched by the notification engine
(low stock, expiry, cold-chain…) for the branch — date, severity, event, channel,
status and message. All values come from the presenter; no SQL, no business
logic. Revisiting the section re-reads the notification log.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class AlertsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryAlertsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Alertas",
            subtitle="Notificaciones de inventario (stock bajo, caducidad, "
                     "cadena de frío) despachadas por el motor de alertas.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"),
            ColumnSpec("Severidad", "status"),
            ColumnSpec("Evento", "text"),
            ColumnSpec("Canal", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Mensaje", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.alerts()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
