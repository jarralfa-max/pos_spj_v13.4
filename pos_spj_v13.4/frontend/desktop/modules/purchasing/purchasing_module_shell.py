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
from frontend.desktop.modules.purchasing.navigation import (
    PurchasingRoutes, visible_routes,
)
from frontend.desktop.modules.purchasing.pages.enterprise_pages import (
    InvoicesPage, OrdersPage, QuotationsPage, RequisitionsPage,
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


class PurchasingModuleShell(QWidget):
    """Single stacked-navigation root for the Procurement desktop experience."""

    def __init__(self, presenter, parent=None, *, direct_purchase_views=None) -> None:
        super().__init__(parent)
        self.setObjectName("purchasingModuleShell")
        self._presenter = presenter
        self._direct_purchase_views = direct_purchase_views or {}
        self._loaded = False
        self._row_to_page: dict[int, int] = {}
        self._route_to_page: dict[str, int] = {}
        self._route_to_row: dict[str, int] = {}
        self._route_badges: dict[str, str] = {}
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

        self._build_navigation(self._direct_purchase_views)
        self.sidebar.currentRowChanged.connect(self._navigate_row)
        self.sidebar.setCurrentRow(next(iter(self._row_to_page)))

    def _group(self, label: str) -> None:
        self.sidebar.add_group(label)

    def _route(self, key: str, label: str, page: QWidget,
               *, badge_key: str | None = None) -> None:
        self.sidebar.add_section(label)
        row = self.sidebar.count() - 1
        page_index = self.content.addWidget(page)
        self._pages.append(page)
        self._row_to_page[row] = page_index
        self._route_to_page[key] = page_index
        self._route_to_row[key] = row
        if badge_key:
            self._route_badges[key] = badge_key

    def _build_navigation(self, direct_purchase_views) -> None:
        capabilities = self._presenter.capabilities()
        if not capabilities.module_view:
            self._group("COMPRAS")
            self._route("no_access", "Sin acceso", create_state_widget(
                ViewState.NO_PERMISSION, self,
                message="No tienes permiso para consultar el módulo de Compras."))
            return
        page_factories = {
            PurchasingRoutes.DASHBOARD: lambda: ProcurementDashboardPage(
                self._presenter, self),
            PurchasingRoutes.REQUISITIONS: self._create_requisitions_page,
            PurchasingRoutes.QUOTATIONS: lambda: QuotationsPage(self._presenter, self),
            PurchasingRoutes.ORDERS: lambda: OrdersPage(self._presenter, self),
            PurchasingRoutes.DIRECT_PURCHASE_CREATE: lambda: direct_purchase_views.get("create"),
            PurchasingRoutes.DIRECT_PURCHASE_HISTORY: lambda: direct_purchase_views.get("history"),
            PurchasingRoutes.ORIGIN_LOADING: lambda: LogisticsRelatedPage(
                self._presenter, self, capabilities=capabilities),
            PurchasingRoutes.RECEIPTS: lambda: PurchaseHistoryPage(
                self._presenter, self),
            PurchasingRoutes.INVOICES: lambda: InvoicesPage(self._presenter, self),
        }
        current_group = None
        for definition in visible_routes(capabilities):
            factory = page_factories.get(definition.key)
            if factory is None:
                continue
            page = factory()
            if page is None:
                continue
            if definition.key == PurchasingRoutes.DASHBOARD:
                page.route_requested.connect(self.navigate_to)
            if definition.group != current_group:
                self._group(definition.group)
                current_group = definition.group
            self._route(definition.key, definition.label, page,
                        badge_key=definition.badge_key)

    def _create_requisitions_page(self):
        page = RequisitionsPage(self._presenter, self)
        page.direct_purchase_requested.connect(self._start_direct_from_requisition)
        return page

    def _start_direct_from_requisition(self, detail: dict) -> None:
        page_index = self._route_to_page.get(PurchasingRoutes.DIRECT_PURCHASE_CREATE)
        if page_index is None:
            return
        self.navigate_to(PurchasingRoutes.DIRECT_PURCHASE_CREATE)
        page = self.content.widget(page_index)
        handler = getattr(page, "start_from_requisition", None)
        if callable(handler):
            handler(detail)

    def navigate_to(self, route_key: str, action: str = "") -> None:
        row = self._route_to_row.get(route_key)
        if row is None:
            return
        self.sidebar.setCurrentRow(row)
        page_index = self._route_to_page[route_key]
        page = self.content.widget(page_index)
        if action:
            handler = getattr(page, f"start_{action}", None)
            if callable(handler):
                handler()

    def refresh_permissions(self) -> None:
        """Reconstruye rutas y botones tras login o un cambio de permisos.

        Compras se construye antes del login (MainWindow arma todas las
        pantallas primero); en ese momento capabilities() está vacío. Este
        método se re-invoca desde MainWindow tras set_permisos() para que el
        sidebar y las acciones reflejen los permisos reales sin reconstruir
        el widget completo.
        """
        current_route = next((key for key, row in self._route_to_row.items()
                              if row == self.sidebar.currentRow()), None)
        for page in self._pages:
            self.content.removeWidget(page)
            if page not in self._direct_purchase_views.values():
                page.deleteLater()
        self._pages.clear()
        self._row_to_page.clear()
        self._route_to_page.clear()
        self._route_to_row.clear()
        self._route_badges.clear()
        self.sidebar.clear()
        self._build_navigation(self._direct_purchase_views)
        if current_route in self._route_to_row:
            self.navigate_to(current_route)
        elif self._row_to_page:
            self.sidebar.setCurrentRow(next(iter(self._row_to_page)))
        for view in self._direct_purchase_views.values():
            refresher = getattr(view, "refresh_permissions", None)
            if callable(refresher):
                refresher()
        self._loaded = False
        self.ensure_loaded()

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
        capabilities = self._presenter.capabilities()
        if not capabilities.module_view:
            self._loaded = True
            return
        kpis = self._presenter.analytics_kpis()
        badges = self._presenter.navigation_badges(kpis)
        for route_key, badge_key in self._route_badges.items():
            self.sidebar.set_badge(self._route_to_row[route_key], badges.get(badge_key, 0))
        self.kpis.set_cards([
            KPIDTO("req", "Solicitudes abiertas", str(kpis.open_requisitions), variant="primary"),
            KPIDTO("approval", "Órdenes por aprobar", str(kpis.pending_order_approvals), variant="warning"),
            KPIDTO("transit", "Órdenes en curso", str(kpis.orders_in_progress), variant="primary"),
            KPIDTO("direct", "Compra directa hoy", str(kpis.direct_purchases_today), variant="primary"),
            KPIDTO("difference", "Facturas con diferencias", str(kpis.invoices_with_differences), variant="danger"),
            KPIDTO("spend", "Gasto comprometido",
                   money(kpis.committed_spend) if capabilities.view_costs else "—",
                   variant="primary",
                   state=KPIState.READY if capabilities.view_costs
                   else KPIState.NO_PERMISSION),
        ])
        self.alerts.set_alerts(self._presenter.analytics_alerts())
        page = self.content.currentWidget()
        reloader = getattr(page, "reload", None)
        if callable(reloader):
            reloader()
        self._loaded = True
