"""ExecutiveDashboardPage (§13, BI-24) — "Resumen ejecutivo": the KPI bar +
charts view fed by `ExecutiveDashboardPresenter`. Mirrors
`frontend/desktop/modules/orders_delivery/pages/analytics_page.py::OrdersAnalyticsPage`
exactly.
"""

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import HtmlChartView, KPIBar, PageHeader, create_secondary_button


class ExecutiveDashboardPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Inteligencia de Negocios — Resumen ejecutivo")
        self.setAccessibleDescription(
            "Indicadores principales, tendencias y evolución del negocio.")
        self._presenter = presenter
        self._loaded = False

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            title="Resumen ejecutivo",
            subtitle="Indicadores principales, tendencias y evolución del negocio.",
            parent=self,
        ))

        actions = QHBoxLayout()
        actions.addStretch(1)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)
        root.addLayout(actions)

        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)

        self.charts: list[HtmlChartView] = []
        self._charts_layout = QVBoxLayout()
        root.addLayout(self._charts_layout, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self) -> None:
        try:
            cards = self._presenter.kpi_cards()
            charts = self._presenter.charts()
        except Exception as exc:
            QMessageBox.warning(self, "Resumen ejecutivo", str(exc))
            return

        self.kpis.set_cards(cards)

        while len(self.charts) < len(charts):
            view = HtmlChartView(self)
            self.charts.append(view)
            self._charts_layout.addWidget(view, stretch=1)
        for view, dto in zip(self.charts, charts):
            view.set_chart(dto)
