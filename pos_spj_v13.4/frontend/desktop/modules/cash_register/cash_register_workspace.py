"""CASH-23 enterprise workspace for cash register UI/UX.

The workspace owns navigation, page hosting, responsive behavior, accessible
metadata and neutral view states. It deliberately does not persist data, execute
SQL or run business decisions; concrete pages emit signals to presenters/use
cases.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.cash_register.blind_count_page import BlindCountPage
from frontend.desktop.modules.cash_register.cash_configuration_page import CashConfigurationPage
from frontend.desktop.modules.cash_register.cash_devices_page import CashDevicesPage
from frontend.desktop.modules.cash_register.cash_ledger_page import CashLedgerPage
from frontend.desktop.modules.cash_register.cash_register_routes import CASH_REGISTER_ROUTES, grouped_routes
from frontend.desktop.themes.tokens import ResponsiveBreakpoints, Spacing


class CashRegisterWorkspace(QWidget):
    """Responsive module shell for Caja."""

    def __init__(self, container=None, parent=None, *, page_factories: dict[str, Callable] | None = None):
        super().__init__(parent)
        self.container = container
        self._page_factories = page_factories or {}
        self._route_index_by_key: dict[str, int] = {}
        self.setObjectName("cashRegisterWorkspace")
        self.setAccessibleName("Modulo de Caja")

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL,
                                Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL)
        root.setSpacing(Spacing.MD)

        refresh = create_secondary_button(
            self,
            "Actualizar",
            tooltip="Recargar la vista activa sin cambiar de seccion.",
        )
        refresh.clicked.connect(self.refresh_active_page)
        root.addWidget(PageHeader(
            self,
            title="Caja",
            subtitle="Operacion, cortes, diferencias, entregas y configuracion con tema JUANIS.",
            actions=[refresh],
        ))

        self._status_bar = KPIBar(self)
        self._status_bar.set_cards([
            KPIDTO("shift", "Turno", "Sin seleccionar"),
            KPIDTO("offline", "Sincronizacion", "Lista"),
            KPIDTO("alerts", "Alertas", "0"),
        ])
        root.addWidget(self._status_bar)

        shell = QHBoxLayout()
        shell.setSpacing(Spacing.LG)
        root.addLayout(shell, stretch=1)

        self._nav = SideNav(self)
        self._nav.setProperty("role", "nav")
        self._nav.setAccessibleName("Navegacion de caja")
        self._nav.navigated.connect(self._on_navigated)
        shell.addWidget(self._nav)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("cashRegisterStack")
        self._stack.setAccessibleName("Paginas del modulo de caja")
        shell.addWidget(self._stack, stretch=1)

        self._build_routes()
        self.select_route("overview")

    def _build_routes(self) -> None:
        row = 0
        page_index = 0
        for group, routes in grouped_routes():
            self._nav.add_group(group)
            row += 1
            for route in routes:
                self._nav.add_section(route.label)
                item = self._nav.item(row)
                if item is not None:
                    item.setToolTip(route.tooltip)
                    item.setData(Qt.UserRole, route.key)
                    item.setData(Qt.AccessibleDescriptionRole, route.tooltip)
                self._route_index_by_key[route.key] = page_index
                self._stack.addWidget(self._wrap_page(route.key, route.label, route.tooltip))
                row += 1
                page_index += 1

    def _wrap_page(self, key: str, label: str, tooltip: str) -> QWidget:
        page = QFrame(self)
        page.setObjectName("cashRegisterPageHost")
        page.setAccessibleName(label)
        page.setAccessibleDescription(tooltip)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        content = self._create_page(key, label, tooltip)
        scroll = QScrollArea(page)
        scroll.setObjectName("cashRegisterScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    def _create_page(self, key: str, label: str, tooltip: str) -> QWidget:
        if key in self._page_factories:
            return self._page_factories[key](self)

        query_service = self._resolve_query_service(key)
        if key == "configuration" and query_service is not None:
            return CashConfigurationPage(query_service, self)
        if key == "hardware" and query_service is not None:
            return CashDevicesPage(query_service, self)
        if key == "ledger" and query_service is not None and self._active_shift_id():
            return CashLedgerPage(query_service, shift_id=self._active_shift_id(), parent=self)
        if key == "blind_count" and query_service is not None and self._active_count_context():
            count_id, branch_id, user_id = self._active_count_context()
            return BlindCountPage(query_service, count_id=count_id, branch_id=branch_id,
                                  requester_user_id=user_id, parent=self)

        placeholder = create_state_widget(
            ViewState.EMPTY,
            self,
            message=f"{label}: vista preparada. Conecta su QueryService para cargar datos.",
        )
        apply_tooltip(placeholder, tooltip, help_id=f"cash_register.{key}")
        return placeholder

    def _resolve_query_service(self, key: str):
        candidates = {
            "configuration": ("cash_configuration_query_service", "cash_register_configuration_query"),
            "hardware": ("cash_devices_query_service", "cash_hardware_query_service"),
            "ledger": ("cash_ledger_query_service", "cash_register_ledger_query"),
            "blind_count": ("blind_count_query_service", "cash_blind_count_query_service"),
        }.get(key, ())
        for name in candidates:
            service = getattr(self.container, name, None)
            if service is not None:
                return service
        return None

    def _active_shift_id(self) -> str | None:
        value = getattr(self.container, "active_cash_shift_id", None)
        return str(value) if value else None

    def _active_count_context(self) -> tuple[str, str, str] | None:
        count_id = getattr(self.container, "active_cash_count_id", None)
        branch_id = getattr(self.container, "active_branch_id", None)
        user_id = getattr(self.container, "current_user_id", None)
        if count_id and branch_id and user_id:
            return str(count_id), str(branch_id), str(user_id)
        return None

    def _on_navigated(self, nav_row: int) -> None:
        item = self._nav.item(nav_row)
        key = item.data(Qt.UserRole) if item is not None else None
        if key in self._route_index_by_key:
            self._stack.setCurrentIndex(self._route_index_by_key[key])

    def select_route(self, key: str) -> None:
        target_index = self._route_index_by_key.get(key)
        if target_index is None:
            return
        for row in range(self._nav.count()):
            item = self._nav.item(row)
            if item is not None and item.data(Qt.UserRole) == key:
                self._nav.select(row)
                break
        self._stack.setCurrentIndex(target_index)

    def refresh_active_page(self) -> None:
        host = self._stack.currentWidget()
        if host is None:
            return
        scroll = host.findChild(QScrollArea)
        page = scroll.widget() if scroll is not None else None
        if page is not None and hasattr(page, "refresh"):
            page.refresh()

    def set_status(self, *, shift: str, sync: str, alerts: int) -> None:
        self._status_bar.set_cards([
            KPIDTO("shift", "Turno", shift),
            KPIDTO("offline", "Sincronizacion", sync),
            KPIDTO("alerts", "Alertas", str(max(0, int(alerts or 0)))),
        ])

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < ResponsiveBreakpoints.COMPACT
        self._nav.setMaximumWidth(180 if compact else 240)
        self._nav.setMinimumWidth(160 if compact else 180)
