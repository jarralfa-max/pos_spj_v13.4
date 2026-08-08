"""Enterprise purchasing shell: sidebar, global context, KPIs and routed content."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget,
)

from frontend.desktop.components import (
    AlertCard, DateRangeFilter, KPIBar, KPIDTO, KPIState, PageHeader, SearchableComboBox, SideNav,
    ViewState, create_primary_button, create_state_widget,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.enterprise_view_models import money
from frontend.desktop.modules.purchasing.pages.enterprise_pages import (
    InvoicesPage, OrdersPage, RequisitionsPage,
)
from frontend.desktop.modules.purchasing.pages.procurement_dashboard_page import (
    ProcurementDashboardPage,
)
from frontend.desktop.modules.purchasing.pages.purchase_history_page import PurchaseHistoryPage
from frontend.desktop.modules.purchasing.pages.logistics_related_page import LogisticsRelatedPage
from frontend.desktop.themes.tokens import SidebarMetrics, Spacing


class ContextFilters(QFrame):
    """Read-only session scope plus a canonical period filter."""

    def __init__(self, session: dict[str, str | bool], warehouses, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("purchasingContextFilters")
        row = QHBoxLayout(self)
        row.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        label = QLabel(f"Sucursal: {session['branch']}", self)
        label.setProperty("role", "muted")
        row.addWidget(label)
        self.warehouse = SearchableComboBox(self, placeholder="Selecciona almacén…")
        self.warehouse.set_options(warehouses)
        if session["warehouse_selected"]:
            self.warehouse.set_current_id(session["warehouse"])
        row.addWidget(self.warehouse)
        row.addStretch(1)
        self.period = DateRangeFilter(self)
        row.addWidget(self.period)


class AlertsBar(QFrame):
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


class _PendingPage(QWidget):
    def __init__(self, title: str, message: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.addWidget(PageHeader(title=title, subtitle=message, icon=Icons.PURCHASES,
                                    compact=True))
        layout.addWidget(create_state_widget(ViewState.EMPTY, self, message=message), stretch=1)


class PurchasingModuleShell(QWidget):
    """Single stacked-navigation root for the Procurement desktop experience."""

    def __init__(self, presenter, parent=None, *, direct_purchase_view=None) -> None:
        super().__init__(parent)
        self.setObjectName("purchasingModuleShell")
        self._presenter = presenter
        self._loaded = False
        self._row_to_page: dict[int, int] = {}
        self._pages: list[QWidget] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = SideNav(self)
        self.sidebar.setMinimumWidth(SidebarMetrics.WIDTH)
        root.addWidget(self.sidebar)

        body = QWidget(self)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        body_layout.setSpacing(Spacing.MD)
        session = presenter.session_summary()
        self.header = PageHeader(
            title="Compras", subtitle=f"Resumen / Operación · {session['user']}",
            icon=Icons.PURCHASES, compact=True)
        refresh = create_primary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        self.header.add_action(refresh)
        body_layout.addWidget(self.header)
        self.filters = ContextFilters(session, presenter.warehouse_options(), self)
        self.filters.period.range_changed.connect(self._period_changed)
        self.filters.warehouse.selection_changed.connect(self._warehouse_changed)
        body_layout.addWidget(self.filters)
        self._warehouse_notice = QLabel(
            "Selecciona un almacén para consultar embarques o ejecutar operaciones logísticas.",
            self)
        self._warehouse_notice.setObjectName("purchasingWarehouseNotice")
        self._warehouse_notice.setProperty("state", "WARNING")
        self._warehouse_notice.setWordWrap(True)
        self._warehouse_notice.setVisible(not session["warehouse_selected"])
        body_layout.addWidget(self._warehouse_notice)
        self.kpis = KPIBar(self, cards=[])
        body_layout.addWidget(self.kpis)
        self.alerts = AlertsBar(self)
        body_layout.addWidget(self.alerts)
        self.content = QStackedWidget(self)
        body_layout.addWidget(self.content, stretch=1)
        root.addWidget(body, stretch=1)

        self._build_navigation(direct_purchase_view)
        self.sidebar.currentRowChanged.connect(self._navigate_row)
        self.sidebar.setCurrentRow(next(iter(self._row_to_page)))

    def _group(self, label: str) -> None:
        self.sidebar.add_group(label)

    def _route(self, label: str, page: QWidget) -> None:
        self.sidebar.add_section(label)
        page_index = self.content.addWidget(page)
        self._pages.append(page)
        self._row_to_page[self.sidebar.count() - 1] = page_index

    def _placeholder(self, title: str, message: str) -> QWidget:
        return _PendingPage(title, message, self)

    def _build_navigation(self, direct_purchase_view) -> None:
        self._group("NAVEGACIÓN")
        self._route("Resumen", ProcurementDashboardPage(self._presenter, self))
        self._group("OPERACIÓN")
        self._route("Solicitudes", RequisitionsPage(self._presenter, self))
        self._route("Cotizaciones", self._placeholder(
            "Cotizaciones", "RFQ, invitaciones y cotizaciones relacionadas."))
        self._route("Adjudicaciones", self._placeholder(
            "Adjudicaciones", "Comparación comercial y decisiones auditadas."))
        self._route("Órdenes de compra", OrdersPage(self._presenter, self))
        if direct_purchase_view is not None:
            self._route("Compra directa", direct_purchase_view)
        self._group("CARGA EN ORIGEN")
        self._route("Embarques relacionados", LogisticsRelatedPage(self._presenter, self))
        self._route("Compras móviles", self._placeholder(
            "Compras móviles", "La PWA está disponible en /mobile/logistics/."))
        self._route("Contenedores asignados", self._placeholder(
            "Contenedores asignados", "Custodia y árbol logístico por embarque."))
        self._group("RECEPCIÓN RELACIONADA")
        self._route("Pendientes y calidad", PurchaseHistoryPage(self._presenter, self))
        self._group("FACTURACIÓN")
        self._route("Facturas y conciliación", InvoicesPage(self._presenter, self))
        self._group("ANALÍTICA")
        self._route("Gasto y desempeño", ProcurementDashboardPage(self._presenter, self))
        self._group("CONFIGURACIÓN")
        self._route("Políticas y tolerancias", self._placeholder(
            "Políticas y tolerancias", "Configuración central de routing, límites y tolerancias."))

    def _navigate_row(self, row: int) -> None:
        page_index = self._row_to_page.get(row)
        if page_index is None:
            return
        self.content.setCurrentIndex(page_index)
        page = self.content.widget(page_index)
        loader = getattr(page, "ensure_loaded", None)
        if callable(loader):
            loader()

    def _period_changed(self, period) -> None:
        self._presenter.set_period(period.start.toString("yyyy-MM-dd"),
                                   period.end.toString("yyyy-MM-dd"))
        page = self.content.currentWidget()
        reloader = getattr(page, "reload", None)
        if callable(reloader):
            reloader()

    def _warehouse_changed(self, warehouse_id) -> None:
        if not warehouse_id:
            return
        try:
            self._presenter.select_warehouse(str(warehouse_id))
        except PermissionError as exc:
            self._warehouse_notice.setText(str(exc))
            self._warehouse_notice.show()
            return
        self._warehouse_notice.hide()
        page = self.content.currentWidget()
        reloader = getattr(page, "reload", None)
        if callable(reloader):
            reloader()

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        kpis = self._presenter.analytics_kpis()
        self.kpis.set_cards([
            KPIDTO("req", "Solicitudes abiertas", str(kpis.open_requisitions), variant="primary"),
            KPIDTO("approval", "Órdenes por aprobar", str(kpis.pending_order_approvals), variant="warning"),
            KPIDTO("transit", "Órdenes en curso", str(kpis.orders_in_progress), variant="primary"),
            KPIDTO("direct", "Compra directa hoy", str(kpis.direct_purchases_today), variant="primary"),
            KPIDTO("difference", "Facturas con diferencias", str(kpis.invoices_with_differences), variant="danger"),
            KPIDTO("spend", "Gasto comprometido",
                   money(kpis.committed_spend) if self._presenter.can("procurement.cost.view") else "—",
                   variant="primary",
                   state=KPIState.READY if self._presenter.can("procurement.cost.view")
                   else KPIState.NO_PERMISSION),
        ])
        self.alerts.set_alerts(self._presenter.analytics_alerts())
        page = self.content.currentWidget()
        reloader = getattr(page, "reload", None)
        if callable(reloader):
            reloader()
        self._loaded = True
