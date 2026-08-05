"""Alerts page (INV-25 / §23) — recent inventory alerts with severity filter.

Presentation-only: a ``KPIBar`` summarizes alert counts by severity and a
``SearchInput`` filters the feed by severity (crítica / advertencia /
informativa). Below, a table lists the alerts dispatched by the notification
engine (low stock, expiry, cold-chain…) for the branch — date, severity, event,
channel, status and message. All values come from the presenter; no SQL, no
business logic. Revisiting or filtering re-reads the notification log.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    KPIBar,
    KPIDTO,
    PageHeader,
    SearchInput,
    StandardTable,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.view_models import severity_filter_code
from frontend.desktop.themes.tokens import Spacing


class AlertsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryAlertsPage")
        self._presenter = presenter
        self._severity = None  # filtro activo (código) o None = todas

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Alertas",
            subtitle="Notificaciones de inventario (stock bajo, caducidad, "
                     "cadena de frío) despachadas por el motor de alertas.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._kpi_bar = KPIBar(cards=[])
        layout.addWidget(self._kpi_bar)

        self._search = SearchInput(
            placeholder="Filtrar por severidad: crítica / advertencia / informativa…")
        self._search.search_submitted.connect(self._on_search)
        layout.addWidget(self._search)

        self._table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"),
            ColumnSpec("Severidad", "status"),
            ColumnSpec("Evento", "text"),
            ColumnSpec("Canal", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Mensaje", "text"),
        ])
        layout.addWidget(self._table)

    def _on_search(self, text: str) -> None:
        # término vacío o no reconocido → sin filtro (todas las severidades)
        self._severity = severity_filter_code(text)
        self.refresh()

    def refresh(self) -> None:
        self._kpi_bar.set_cards([
            KPIDTO(key=k.key, title=k.title, value=k.value, variant=k.variant,
                   tooltip=k.tooltip) for k in self._presenter.alert_kpis()])
        table = self._presenter.alerts(severity=self._severity)
        self._table.load_rows(table.rows, row_ids=table.row_ids)
