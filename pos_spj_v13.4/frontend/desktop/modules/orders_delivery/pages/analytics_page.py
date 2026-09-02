"""OrdersAnalyticsPage (ORD-28) — "Análisis": KPI bar + real charts, closing
the "Charts" gap ORD-27 (backend-only analytics) deliberately left open.
Mirrors `frontend/desktop/modules/losses/pages/analytics_page.py`'s shape.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import HtmlChartView, KPIBar, PageHeader, create_secondary_button


class OrdersAnalyticsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Análisis de Pedidos y Delivery")
        self._presenter = presenter
        self._loaded = False

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            title="Análisis", subtitle="Tendencias y desempeño de pedidos y entregas.",
            parent=self))
        actions = QHBoxLayout()
        actions.addStretch(1)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)
        root.addLayout(actions)
        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)
        self.charts = [HtmlChartView(self) for _ in range(2)]
        for chart in self.charts:
            root.addWidget(chart, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self) -> None:
        try:
            cards = self._presenter.kpi_cards()
            charts = self._presenter.charts()
        except Exception as exc:  # noqa: BLE001 - surface, never crash the page
            QMessageBox.warning(self, "Análisis", str(exc))
            return
        self.kpis.set_cards(cards)
        for view, dto in zip(self.charts, charts):
            view.set_chart(dto)
