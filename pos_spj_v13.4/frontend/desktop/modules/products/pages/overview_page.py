"""Products overview page (§43) — KPI bar + recent alerts.

UI only: all values come from the presenter. Renders the JUANIS PageHeader, a
KPIBar of catalog health and a StandardTable of recent alerts. No SQL, no
business logic, no local styles.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    KPIBar,
    KPIDTO,
    PageHeader,
    StandardTable,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing



class ProductsOverviewPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productsOverviewPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Resumen de Productos",
            subtitle="Salud del catálogo: activos, cárnicos, internos e incompletos.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        layout.addWidget(self.header)

        self.kpi_bar = KPIBar()
        layout.addWidget(self.kpi_bar)

        self.alerts = StandardTable(columns=[
            ColumnSpec("Severidad", "severity"),
            ColumnSpec("Tipo", "alert_type"),
            ColumnSpec("Mensaje", "message"),
        ])
        layout.addWidget(self.alerts, 1)
        self.refresh()

    def refresh(self) -> None:
        self.kpi_bar.set_cards([
            KPIDTO(key=k.key, title=k.title, value=k.value, variant=k.variant)
            for k in self._presenter.overview_kpis()])
        table = self._presenter.recent_alerts()
        self.alerts.load_rows(table.rows, row_ids=table.row_ids)
