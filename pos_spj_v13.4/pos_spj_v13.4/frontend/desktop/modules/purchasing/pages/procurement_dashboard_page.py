"""Procurement analytics dashboard (PUR-12) — KPIBar + ECharts cards.

UI only: KPIs and color-free ChartDataDTOs come from the presenter/analytics
service. Charts render via HtmlChartView (ECharts) and degrade to a table when
QtWebEngine is unavailable (headless / accessibility).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ChartCard,
    DashboardGrid,
    HtmlChartView,
    KPIBar,
    KPIDTO,
    PageHeader,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.enterprise_view_models import money
from frontend.desktop.themes.tokens import Spacing


class ProcurementDashboardPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("procurementDashboardPage")
        self._presenter = presenter
        self._loaded = False
        self._chart_views: list[HtmlChartView] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Analítica de Compras",
            subtitle="Solicitudes, órdenes, recepción y facturación en un vistazo.",
            icon=Icons.PURCHASES, compact=True)
        layout.addWidget(self.header)
        self._status = QLabel("", self)
        self._status.setObjectName("procurementDashboardStatus")
        self._status.setProperty("state", "ERROR")
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self._grid = DashboardGrid(self)
        self._kpi_bar = KPIBar(cards=[])
        self._grid.add_kpi_bar(self._kpi_bar)

        self._cards: list[ChartCard] = []
        for _ in range(3):
            card = ChartCard(self)
            view = HtmlChartView(card)
            card.add(view)
            self._chart_views.append(view)
            self._cards.append(card)
        self._grid.add_row((self._cards[0], 2), (self._cards[1], 1))
        self._grid.add_full_width(self._cards[2])
        self._grid.add_stretch()
        layout.addWidget(self._grid, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        self._status.setText("Cargando indicadores de Compras…")
        self._status.setProperty("state", "LOADING")
        self._status.show()
        try:
            kpis = self._presenter.analytics_kpis()
            self._kpi_bar.set_cards([
                KPIDTO(key="req", title="Solicitudes abiertas",
                       value=str(kpis.open_requisitions), variant="primary"),
                KPIDTO(key="appr", title="Órdenes por aprobar",
                       value=str(kpis.pending_order_approvals), variant="warning"),
                KPIDTO(key="prog", title="Órdenes en curso",
                       value=str(kpis.orders_in_progress), variant="primary"),
                KPIDTO(key="rec", title="Recepciones completadas",
                       value=str(kpis.receipts_completed), variant="success"),
                KPIDTO(key="diff", title="Facturas con diferencias",
                       value=str(kpis.invoices_with_differences), variant="danger"),
                KPIDTO(key="spend", title="Gasto comprometido",
                       value=money(kpis.committed_spend), variant="primary"),
            ])
            charts = self._presenter.analytics_charts()
            for view, dto in zip(self._chart_views, charts):
                view.set_chart(dto)
            self._loaded = True
            self._status.hide()
        except Exception as exc:
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar la analítica: {exc}")
