"""Inventory analytics page (INV-24) — KPIs + ECharts (degrade to table).

UI only: KPIs and color-free ChartDataDTOs come from the presenter/analytics
service. Charts render via HtmlChartView and degrade to a table when QtWebEngine
is unavailable (headless / accessibility). Export delegates to the presenter.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    HtmlChartView,
    KPIBar,
    KPIDTO,
    PageHeader,
    create_secondary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class InventoryAnalyticsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryAnalyticsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Analítica de Inventario",
            subtitle="Existencias, movimientos y merma en un vistazo.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.export_button = create_secondary_button(text="Exportar CSV")
        self.export_button.clicked.connect(self._on_export)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)

        self._kpi_bar = KPIBar(cards=[])
        layout.addWidget(self._kpi_bar)

        self._chart_views: list[HtmlChartView] = [HtmlChartView() for _ in range(4)]
        for view in self._chart_views:
            layout.addWidget(view, stretch=1)

        self.last_export = ""

    def refresh(self) -> None:
        kpis = self._presenter.inventory_kpis()
        self._kpi_bar.set_cards([
            KPIDTO(key=k.key, title=k.title, value=k.value, variant=k.variant,
                   tooltip=k.tooltip) for k in kpis])
        for view, dto in zip(self._chart_views, self._presenter.analytics_charts()):
            view.set_chart(dto)

    def _on_export(self) -> None:
        try:
            self.last_export = self._presenter.export_availability_csv()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Analítica de Inventario",
                                f"No fue posible exportar:\n{exc}")
            return
        QMessageBox.information(self, "Analítica de Inventario",
                                "Disponibilidad exportada a CSV.")
