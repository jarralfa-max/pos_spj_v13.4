"""Resumen financiero (§29.2): 12 KPIs del mes, alertas accionables y las 10
gráficas del módulo (QueryService → ChartDataDTO → HtmlChartView).

La página no calcula nada: pinta el ``FinanceDashboardDTO`` del presenter.
Cada alerta lleva a la sección que la atiende.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.cards import AlertCard, ChartCard
from frontend.desktop.components.chart_view import HtmlChartView
from frontend.desktop.components.dashboard_grid import DashboardGrid
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.themes.tokens import Spacing

_ALERT_VARIANT = {"danger": "danger", "warning": "alert", "info": "info"}
#: Alertas por renglón: ocho en una fila no caben a 1366×768.
_ALERTS_PER_ROW = 4


class OverviewPage(QWidget):
    #: Ruta de la sección que atiende una alerta (``FinanceView.open_route``).
    navigate_requested = pyqtSignal(str)

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("overflowPolicy", "auto")
        self._presenter = presenter
        self._loaded = False
        self._charts: dict[str, HtmlChartView] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        self.header = PageHeader(title="Resumen financiero",
                                 subtitle="Hechos contables del mes en curso", compact=True)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        self.header.add_action(refresh)
        layout.addWidget(self.header)
        self._notice = QLabel("", self)
        self._notice.setWordWrap(True)
        self._notice.hide()
        layout.addWidget(self._notice)
        self._grid = DashboardGrid(self)
        self._kpis = KPIBar(self, cards=[])
        self._grid.add_kpi_bar(self._kpis)
        self._alerts = QWidget(self)
        self._alerts_layout = QGridLayout(self._alerts)
        self._alerts_layout.setContentsMargins(0, 0, 0, 0)
        self._grid.add_full_width(self._alerts)
        self._chart_rows: list[ChartCard] = []
        layout.addWidget(self._grid, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            dashboard = self._presenter.dashboard()
        except Exception as exc:  # la causa se muestra; la página no queda en blanco
            self._notice.setProperty("state", "ERROR")
            self._notice.setText(f"No fue posible cargar el resumen: {exc}")
            self._notice.show()
            return
        self._notice.hide()
        self.header.set_subtitle(f"{dashboard.period_from} a {dashboard.period_to} · "
                                 f"{dashboard.currency_code}")
        self._kpis.set_cards([KPIDTO(key=k.title, title=k.title, value=k.value,
                                     variant=k.variant)
                              for k in self._presenter.kpis(dashboard)])
        self._paint_alerts(self._presenter.alerts(dashboard))
        self._paint_charts(dashboard.charts)
        self._loaded = True

    def _paint_alerts(self, alerts) -> None:
        while self._alerts_layout.count():
            widget = self._alerts_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        if not alerts:
            label = QLabel("Sin alertas pendientes.", self._alerts)
            label.setProperty("role", "muted")
            self._alerts_layout.addWidget(label, 0, 0)
            return
        for index, alert in enumerate(alerts):
            card = AlertCard(self._alerts, variant=_ALERT_VARIANT.get(alert.severity, "alert"))
            button = create_secondary_button(card, f"{alert.label}: {alert.count}")
            button.clicked.connect(lambda _=False, r=alert.route: self.navigate_requested.emit(r))
            card.add(button)
            self._alerts_layout.addWidget(card, index // _ALERTS_PER_ROW,
                                          index % _ALERTS_PER_ROW)

    def _paint_charts(self, charts) -> None:
        pending = list(charts)
        if not self._charts:
            for left, right in zip(pending[::2], pending[1::2] + [None]):
                cards = []
                for dto in (left, right):
                    if dto is None:
                        continue
                    card = ChartCard(self)
                    title = QLabel(dto.title, card)
                    title.setProperty("role", "subtitle")
                    title.setWordWrap(True)
                    view = HtmlChartView(card)
                    view.setMinimumHeight(240)
                    card.add(title)
                    card.add(view)
                    self._charts[dto.chart_id] = view
                    cards.append((card, 1))
                self._grid.add_row(*cards)
        for dto in pending:
            view = self._charts.get(dto.chart_id)
            if view is not None:
                view.set_chart(dto)
