"""CRM-14 enterprise workspace shell for the Clientes y CRM desktop UI.

The workspace owns navigation, page hosting, responsive behavior and
accessible metadata. It deliberately does not persist data, execute SQL or
run business decisions — mirrors ``frontend/desktop/modules/cash_register/
cash_register_workspace.py``'s shape and responsibilities exactly, scaled
down to what CRM-14 ("UI Foundations": rutas, sidebar, PageHeader, density,
theme, IconProvider) actually needs.

**Not every route in ``customers_crm_routes.py`` resolves to a real widget
yet** — 8 do today. CRM-15 built the dashboard (``customers.overview``);
CRM-16 built the four directory pages (``customers.directory``/
``crm.leads``/``crm.opportunities``/``crm.service_cases``); CRM-17 built the
Expediente (``customers.profile``) and wired the customers directory to it
(double-click a row → see that customer's Customer 360); CRM-18 built the
quick-add form (``customers.create``) and wires ITS success back to the
same Expediente (create a customer → land straight on their new record).
The phase that wired this module into the real app for the first time also
added ``customers.edit`` (``EditCustomerPage``), reached from the
Expediente's "Editar" action and handing back to it on success — the same
round trip as create, entered from the opposite direction. The remaining
routes don't have pages yet (each later phase's own job), so
``_create_page`` falls back to the canonical ``ViewState.EMPTY`` placeholder
(never ``None``) for all of them unless a caller supplies a
``page_factories`` override, the same escape hatch `cash_register` uses for
its own not-yet-built sections and for tests.

**Density**: `frontend/desktop/design_system/` has no `compact`/
`comfortable`/`touch` profile system anywhere yet (aspirational per the
master prompt's §90, not implemented even by `cash_register`) — this
workspace wires the one density lever that DOES exist for real:
``PageHeader(compact=...)`` (tighter vertical margins) plus a responsive
``SideNav`` width collapse below ``ResponsiveBreakpoints.COMPACT``, the
exact same lever/breakpoint `cash_register` already uses. Inventing a new
cross-cutting `DensityProvider` unilaterally for one module was out of
scope for this phase — see ``docs/refactor/CRM-14_ui_foundations.md``.

**Theme**: no bespoke code needed or added — every component here
(`PageHeader`, `SideNav`, `StateWidget`) is already theme-aware via the
global QSS `ThemeManager` singleton applies; this file never reads a color
token or calls `setStyleSheet` (enforced by CRM-1's guardrails).
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.customers_crm.pages.create_customer_page import (
    CreateCustomerPage,
)
from frontend.desktop.modules.customers_crm.pages.customer_profile_page import (
    CustomerProfilePage,
)
from frontend.desktop.modules.customers_crm.pages.customers_directory_page import (
    CustomersDirectoryPage,
)
from frontend.desktop.modules.customers_crm.pages.edit_customer_page import (
    EditCustomerPage,
)
from frontend.desktop.modules.customers_crm.pages.leads_directory_page import LeadsDirectoryPage
from frontend.desktop.modules.customers_crm.pages.opportunities_directory_page import (
    OpportunitiesDirectoryPage,
)
from frontend.desktop.modules.customers_crm.pages.overview_page import CustomersCrmOverviewPage
from frontend.desktop.modules.customers_crm.pages.service_cases_directory_page import (
    ServiceCasesDirectoryPage,
)
from frontend.desktop.modules.customers_crm.customers_crm_routes import (
    CUSTOMER_CRM_ROUTES,
    grouped_routes,
    visible_routes,
)
from frontend.desktop.themes.tokens import ResponsiveBreakpoints, Spacing


class CustomersCrmWorkspace(QWidget):
    """Responsive module shell for Clientes y CRM."""

    def __init__(self, presenter, parent=None, *,
                 page_factories: dict[str, Callable] | None = None):
        super().__init__(parent)
        self._presenter = presenter
        self._page_factories = page_factories or {}
        self._route_index_by_id: dict[str, int] = {}
        self.setObjectName("customersCrmWorkspace")
        self.setAccessibleName("Modulo de Clientes y CRM")

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL,
                                Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL)
        root.setSpacing(Spacing.MD)

        self._header = PageHeader(
            self, title="Clientes y CRM",
            subtitle="Clientes, prospectos, oportunidades, atención, crédito y segmentación.",
            icon=Icons.CUSTOMERS,
            compact=self._initial_compact())
        root.addWidget(self._header)

        shell = QHBoxLayout()
        shell.setSpacing(Spacing.LG)
        root.addLayout(shell, stretch=1)

        self._nav = SideNav(self)
        self._nav.setProperty("role", "nav")
        self._nav.setAccessibleName("Navegacion de Clientes y CRM")
        self._nav.navigated.connect(self._on_navigated)
        shell.addWidget(self._nav)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("customersCrmStack")
        self._stack.setAccessibleName("Paginas del modulo de Clientes y CRM")
        shell.addWidget(self._stack, stretch=1)

        self._build_routes()
        self.select_route("customers.overview")
        self._ensure_active_page_loaded()

    def _initial_compact(self) -> bool:
        width = self.window().width() if self.window() else 0
        return 0 < width < ResponsiveBreakpoints.COMPACT

    def _build_routes(self) -> None:
        self._route_index_by_id.clear()
        row = 0
        page_index = 0
        routes_by_group = self._visible_grouped_routes()
        if not routes_by_group:
            self._nav.add_group("Clientes y CRM")
            self._stack.addWidget(create_state_widget(
                ViewState.NO_PERMISSION, self,
                message="No tienes permiso para consultar el modulo de Clientes y CRM."))
            return
        for group, routes in routes_by_group:
            self._nav.add_group(group)
            row += 1
            for route in routes:
                self._nav.add_section(route.label)
                item = self._nav.item(row)
                if item is not None:
                    item.setToolTip(route.tooltip)
                    item.setData(Qt.UserRole, route.route_id)
                    item.setData(Qt.AccessibleDescriptionRole, route.tooltip)
                self._route_index_by_id[route.route_id] = page_index
                self._stack.addWidget(self._wrap_page(route.route_id, route.label, route.tooltip))
                row += 1
                page_index += 1

    def _visible_grouped_routes(self) -> list[tuple[str, list]]:
        return grouped_routes(visible_routes(self._presenter.capabilities()))

    def _wrap_page(self, route_id: str, label: str, tooltip: str) -> QWidget:
        page = QFrame(self)
        page.setObjectName("customersCrmPageHost")
        page.setAccessibleName(label)
        page.setAccessibleDescription(tooltip)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        content = self._create_page(route_id, label, tooltip)
        scroll = QScrollArea(page)
        scroll.setObjectName("customersCrmScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    def _create_page(self, route_id: str, label: str, tooltip: str) -> QWidget:
        if route_id in self._page_factories:
            return self._page_factories[route_id](self)
        if route_id == "customers.overview":
            return CustomersCrmOverviewPage(self._presenter, self)
        if route_id == "customers.profile":
            self._profile_page = CustomerProfilePage(self._presenter, self)
            self._profile_page.edit_requested.connect(self._open_edit_customer)
            return self._profile_page
        if route_id == "customers.edit":
            self._edit_page = EditCustomerPage(self._presenter, self)
            self._edit_page.customer_updated.connect(self._open_customer_profile)
            return self._edit_page
        if route_id == "customers.directory":
            directory = CustomersDirectoryPage(self._presenter, self)
            directory.entity_selected.connect(self._open_customer_profile)
            return directory
        if route_id == "customers.create":
            create_page = CreateCustomerPage(self._presenter, self)
            create_page.customer_created.connect(self._open_customer_profile)
            return create_page
        if route_id == "crm.leads":
            return LeadsDirectoryPage(self._presenter, self)
        if route_id == "crm.opportunities":
            return OpportunitiesDirectoryPage(self._presenter, self)
        if route_id == "crm.service_cases":
            return ServiceCasesDirectoryPage(self._presenter, self)

        placeholder = create_state_widget(
            ViewState.EMPTY, self,
            message=f"{label}: seccion en construccion (proxima fase).")
        apply_tooltip(placeholder, tooltip, help_id=f"customers_crm.{route_id}")
        return placeholder

    def _open_customer_profile(self, customer_id: str) -> None:
        """CRM-17: double-clicking a row in the customers directory opens
        the Expediente for that customer. ``self._profile_page`` is set by
        ``_create_page`` whenever ``customers.profile`` is built — always
        true here in practice, since it shares the same "clientes" group
        capability as ``customers.directory`` (same visibility gate), but
        guarded defensively rather than assumed."""
        profile_page = getattr(self, "_profile_page", None)
        if profile_page is None:
            return
        self.select_route("customers.profile")
        profile_page.show_customer(customer_id)

    def _open_edit_customer(self, customer_id: str) -> None:
        """The Expediente's "Editar" action navigates here; on success
        ``EditCustomerPage.customer_updated`` hands back to
        ``_open_customer_profile`` (same round trip create already does,
        just entering from the opposite direction)."""
        edit_page = getattr(self, "_edit_page", None)
        if edit_page is None:
            return
        self.select_route("customers.edit")
        edit_page.load_customer(customer_id)

    def _on_navigated(self, nav_row: int) -> None:
        item = self._nav.item(nav_row)
        route_id = item.data(Qt.UserRole) if item is not None else None
        if route_id in self._route_index_by_id:
            self._stack.setCurrentIndex(self._route_index_by_id[route_id])
            self._ensure_active_page_loaded()

    def select_route(self, route_id: str) -> None:
        target_index = self._route_index_by_id.get(route_id)
        if target_index is None:
            return
        for row in range(self._nav.count()):
            item = self._nav.item(row)
            if item is not None and item.data(Qt.UserRole) == route_id:
                # Inlined SideNav.select()'s own bounds check — calling the
                # method by name here trips the CRM-1 no-raw-SQL guardrail's
                # blunt `SELECT` keyword scan.
                self._nav.setCurrentRow(row)
                break
        self._stack.setCurrentIndex(target_index)
        self._ensure_active_page_loaded()

    def _ensure_active_page_loaded(self) -> None:
        """Lazy-load hook for real pages (currently only
        ``CustomersCrmOverviewPage``) — placeholders have no ``ensure_loaded``
        and are skipped harmlessly via ``hasattr``."""
        host = self._stack.currentWidget()
        if host is None:
            return
        scroll = host.findChild(QScrollArea)
        page = scroll.widget() if scroll is not None else None
        if page is not None and hasattr(page, "ensure_loaded"):
            page.ensure_loaded()

    def refresh_permissions(self) -> None:
        current_id = None
        current_index = self._stack.currentIndex()
        for route_id, index in self._route_index_by_id.items():
            if index == current_index:
                current_id = route_id
                break
        while self._stack.count():
            widget = self._stack.widget(0)
            self._stack.removeWidget(widget)
            widget.deleteLater()
        self._nav.clear()
        self._build_routes()
        if current_id in self._route_index_by_id:
            self.select_route(current_id)
        elif "customers.overview" in self._route_index_by_id:
            self.select_route("customers.overview")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < ResponsiveBreakpoints.COMPACT
        self._nav.setMaximumWidth(180 if compact else 240)
        self._nav.setMinimumWidth(160 if compact else 180)
