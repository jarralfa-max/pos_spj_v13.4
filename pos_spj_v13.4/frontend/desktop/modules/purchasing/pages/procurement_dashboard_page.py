"""Procurement analytics dashboard (PUR-12) — KPIBar + ECharts cards.

UI only: KPIs and color-free ChartDataDTOs come from the presenter/analytics
service. Charts render via HtmlChartView (ECharts) and degrade to a table when
QtWebEngine is unavailable (headless / accessibility).
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    AlertCard,
    ChartCard,
    DashboardGrid,
    HtmlChartView,
    KPIBar,
    KPIDTO,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.modules.purchasing.enterprise_view_models import money
from frontend.desktop.modules.purchasing.navigation import PurchasingRoutes
from frontend.desktop.themes.tokens import Spacing


class AlertsBar(QFrame):
    """Moved here from purchasing_module_shell.py (FASE UI chrome cleanup):
    alerts are dashboard content, not global chrome duplicated on every
    routed page."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("purchasingAlertsBar")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(Spacing.SM)

    def set_alerts(self, alerts) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for alert in alerts:
            card = AlertCard(self, variant=alert.severity)
            label = QLabel(f"{alert.count} · {alert.message}", card)
            label.setWordWrap(True)
            card.add(label)
            self._row.addWidget(card, stretch=1)
        self.setVisible(bool(alerts))


class ProcurementDashboardPage(QWidget):
    route_requested = pyqtSignal(str, str)

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("procurementDashboardPage")
        self._presenter = presenter
        self._loaded = False
        self._chart_views: list[HtmlChartView] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        intro = QLabel("Resumen operativo y siguientes acciones", self)
        intro.setObjectName("procurementDashboardIntro")
        intro.setProperty("role", "sectionTitle")
        layout.addWidget(intro)
        layout.addWidget(self._build_quick_actions())
        layout.addWidget(self._build_process_flow())
        self._status = QLabel("", self)
        self._status.setObjectName("procurementDashboardStatus")
        self._status.setProperty("state", "ERROR")
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self._alerts = AlertsBar(self)
        layout.addWidget(self._alerts)

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

    def _request_route(self, route: str, action: str = "") -> None:
        self.route_requested.emit(route, action)

    def _build_quick_actions(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("procurementQuickActions")
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Spacing.SM)
        capabilities = self._presenter.capabilities()
        actions = (
            ("Nueva solicitud", PurchasingRoutes.REQUISITIONS, "create",
             capabilities.requisition_create),
            ("Nueva orden de compra", PurchasingRoutes.ORDERS, "create",
             capabilities.order_create),
            ("Nueva compra directa", PurchasingRoutes.DIRECT_PURCHASE_CREATE, "create",
             capabilities.direct_create),
            ("Capturar factura", PurchasingRoutes.INVOICES, "create",
             capabilities.invoice_capture),
        )
        first = True
        for label, route, action, visible in actions:
            if not visible:
                continue
            factory = create_primary_button if first else create_secondary_button
            button = factory(self, label)
            button.clicked.connect(
                lambda _checked=False, r=route, a=action: self._request_route(r, a))
            row.addWidget(button)
            first = False
        row.addStretch(1)
        frame.setVisible(not first)
        return frame

    def _build_process_flow(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("procurementProcessFlow")
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Spacing.SM)
        capabilities = self._presenter.capabilities()
        stages = (
            ("PR", PurchasingRoutes.REQUISITIONS, capabilities.requisition_view),
            ("PO", PurchasingRoutes.ORDERS, capabilities.order_view),
            ("Carga en origen", PurchasingRoutes.ORIGIN_LOADING, capabilities.origin_view),
            ("Recepción", PurchasingRoutes.RECEIPTS, capabilities.receipt_view),
            ("Factura", PurchasingRoutes.INVOICES, capabilities.invoice_view),
        )
        visible_stages = [(label, route) for label, route, visible in stages if visible]
        for index, (label, route) in enumerate(visible_stages):
            if index:
                arrow = QLabel("→", frame)
                arrow.setProperty("role", "muted")
                row.addWidget(arrow)
            button = create_secondary_button(self, label)
            button.clicked.connect(
                lambda _checked=False, r=route: self._request_route(r))
            row.addWidget(button)
        row.addStretch(1)
        frame.setVisible(bool(visible_stages))
        return frame

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
            self._alerts.set_alerts(self._presenter.analytics_alerts())
            self._loaded = True
            self._status.hide()
        except Exception as exc:
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar la analítica: {exc}")
