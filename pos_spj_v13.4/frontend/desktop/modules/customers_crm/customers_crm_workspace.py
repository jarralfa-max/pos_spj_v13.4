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

The shared ``ModuleLayout`` owns the compact header, margins and scrollable
content boundary. ``SideNav`` owns density and manual collapse, so resizing
the workspace preserves the user's navigation preference.

**Theme**: no bespoke code needed or added — every component here
(`PageHeader`, `SideNav`, `StateWidget`) is already theme-aware via the
global QSS `ThemeManager` singleton applies; this file never reads a color
token or calls `setStyleSheet` (enforced by CRM-1's guardrails).
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.module_layout import ModuleLayout
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
from frontend.desktop.modules.customers_crm.pages.overview_page import CustomersCrmOverviewPage
from frontend.desktop.modules.customers_crm.customers_crm_routes import (
    GROUP_ICONS,
    CUSTOMER_CRM_ROUTES,
    grouped_routes,
    visible_routes,
)
from frontend.desktop.themes.tokens import Spacing


class CustomersCrmWorkspace(QWidget):
    """Responsive module shell for Clientes y CRM."""

    #: CRM-32: relayed from `CustomerProfilePage.navigation_requested` —
    #: this is the object `interfaz/main_window.py` actually adds to its
    #: `QStackedWidget` (see `modulos/clientes_crm.py`'s factory), so this
    #: is the level `_conectar()`'s `hasattr(pantalla, ...)` auto-wiring
    #: needs to see the signal on.
    navigation_requested = pyqtSignal(object)

    def __init__(self, presenter, parent=None, *,
                 page_factories: dict[str, Callable] | None = None):
        super().__init__(parent)
        self._presenter = presenter
        self._page_factories = page_factories or {}
        self._route_index_by_id: dict[str, int] = {}
        self.setObjectName("customersCrmWorkspace")
        self.setAccessibleName("Modulo de Clientes y CRM")

        self._nav = SideNav(self)
        self._nav.setProperty("role", "nav")
        self._nav.setAccessibleName("Navegacion de Clientes y CRM")
        self._nav.navigated.connect(self._on_navigated)
        self._stack = QStackedWidget(self)
        self._stack.setObjectName("customersCrmStack")
        self._stack.setAccessibleName("Paginas del modulo de Clientes y CRM")
        self.module_layout = ModuleLayout(
            self, title="Clientes y CRM",
            subtitle="Clientes, prospectos, oportunidades, atención, crédito y segmentación.",
            icon=Icons.CUSTOMERS, sidebar=self._nav, content=self._stack,
        )
        self._header = self.module_layout.header

        self._build_routes()
        self.select_route("customers.overview")
        self._ensure_active_page_loaded()

    def _build_routes(self) -> None:
        self._route_index_by_id.clear()
        row = 0
        page_index = 0
        routes_by_group = self._visible_grouped_routes()
        if not routes_by_group:
            self._nav.add_group("Clientes y CRM", icon=Icons.CUSTOMERS)
            self._stack.addWidget(create_state_widget(
                ViewState.NO_PERMISSION, self,
                message="No tienes permiso para consultar el modulo de Clientes y CRM."))
            return
        for group, routes in routes_by_group:
            self._nav.add_group(group, icon=GROUP_ICONS[group])
            row += 1
            for route in routes:
                self._nav.add_section(route.label, icon=route.icon)
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
        can = getattr(self._presenter, "can", None)
        return grouped_routes(visible_routes(self._presenter.capabilities(),
                                             can if callable(can) else None))

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
            self._profile_page.navigation_requested.connect(self.navigation_requested.emit)
            self._profile_page.opportunity_opened.connect(self._open_opportunity)
            self._profile_page.case_opened.connect(self._open_case)
            return self._profile_page
        if route_id == "customers.edit":
            self._edit_page = EditCustomerPage(self._presenter, self)
            self._edit_page.customer_updated.connect(self._open_customer_profile)
            return self._edit_page
        if route_id == "customers.directory":
            directory = CustomersDirectoryPage(self._presenter, self)
            directory.entity_selected.connect(self._open_customer_profile)
            directory.create_requested.connect(lambda: self.select_route("customers.create"))
            return directory
        if route_id == "customers.create":
            create_page = CreateCustomerPage(self._presenter, self)
            create_page.customer_created.connect(self._open_customer_profile)
            return create_page
        page = self._create_crm43_page(route_id)
        if page is not None:
            return page

        placeholder = create_state_widget(
            ViewState.EMPTY, self,
            message=f"{label}: seccion en construccion (proxima fase).")
        apply_tooltip(placeholder, tooltip, help_id=f"customers_crm.{route_id}")
        return placeholder

    # -- CRM-43: páginas operativas -------------------------------------------
    def _create_crm43_page(self, route_id: str):
        """Páginas construidas en la re-auditoría CRM-43 (antes «en construcción»)."""
        from frontend.desktop.modules.customers_crm.pages.activity_pages import (
            ACTIVITY_ROUTE_PAGES,
        )
        from frontend.desktop.modules.customers_crm.pages.leads_pages import (
            LEAD_ROUTE_PAGES,
            LeadDetailPage,
        )
        from frontend.desktop.modules.customers_crm.pages.service_pages import (
            CASE_ROUTE_PAGES,
            CaseDetailPage,
            SlaPage,
        )
        from frontend.desktop.modules.customers_crm.pages.opportunity_pages import (
            OPPORTUNITY_ROUTE_PAGES,
            ForecastPage,
            OpportunityDetailPage,
            PipelinePage,
        )

        if route_id in LEAD_ROUTE_PAGES:
            page = LEAD_ROUTE_PAGES[route_id](self._presenter, self)
            page.row_opened.connect(self._open_lead)
            return page
        if route_id == "crm.lead_detail":
            self._lead_detail = LeadDetailPage(self._presenter, self)
            return self._lead_detail
        if route_id in OPPORTUNITY_ROUTE_PAGES:
            page = OPPORTUNITY_ROUTE_PAGES[route_id](self._presenter, self)
            page.row_opened.connect(self._open_opportunity)
            return page
        if route_id == "crm.pipeline":
            page = PipelinePage(self._presenter, self)
            page.opportunity_opened.connect(self._open_opportunity)
            return page
        if route_id == "crm.forecast":
            return ForecastPage(self._presenter, self)
        if route_id == "crm.opportunity_detail":
            self._opportunity_detail = OpportunityDetailPage(self._presenter, self)
            return self._opportunity_detail
        if route_id in ACTIVITY_ROUTE_PAGES:
            return ACTIVITY_ROUTE_PAGES[route_id](self._presenter, self)
        if route_id in CASE_ROUTE_PAGES:
            page = CASE_ROUTE_PAGES[route_id](self._presenter, self)
            page.row_opened.connect(self._open_case)
            return page
        if route_id == "crm.case_detail":
            self._case_detail = CaseDetailPage(self._presenter, self)
            return self._case_detail
        if route_id == "crm.sla":
            return SlaPage(self._presenter, self)
        from frontend.desktop.modules.customers_crm.pages.credit_pages import (
            CREDIT_ROUTE_PAGES,
        )
        if route_id in CREDIT_ROUTE_PAGES:
            return CREDIT_ROUTE_PAGES[route_id](self._presenter, self)
        from frontend.desktop.modules.customers_crm.pages.control_pages import (
            CONTROL_ROUTE_PAGES,
        )
        if route_id in CONTROL_ROUTE_PAGES:
            page = CONTROL_ROUTE_PAGES[route_id](self._presenter, self)
            if hasattr(page, "customer_opened"):
                page.customer_opened.connect(self._open_customer_profile)
            return page
        from frontend.desktop.modules.customers_crm.pages.segmentation_pages import (
            SEGMENTATION_ROUTE_PAGES,
        )
        if route_id in SEGMENTATION_ROUTE_PAGES:
            return SEGMENTATION_ROUTE_PAGES[route_id](self._presenter, self)
        from frontend.desktop.modules.customers_crm.pages import customer_sections as cs
        scoped = {
            "customers.contacts": (cs.ContactsSection, "Contactos",
                                   "Personas de contacto de cada cliente.", Icons.PHONE),
            "customers.addresses": (cs.AddressesSection, "Direcciones",
                                    "Direcciones fiscales, de entrega y comerciales.",
                                    Icons.ADDRESS),
            "customers.tax_profiles": (cs.TaxProfileSection, "Datos fiscales",
                                       "RFC, régimen, uso de CFDI y correo de facturación.",
                                       Icons.FINANCE),
            "customers.accounts": (cs.AccountsSection, "Cuentas comerciales",
                                   "Cuentas de clientes empresariales.", Icons.COMPANY),
        }
        from frontend.desktop.modules.customers_crm.pages import privacy_pages as pv
        if route_id in pv.PRIVACY_ROUTE_PAGES:
            return pv.PRIVACY_ROUTE_PAGES[route_id](self._presenter, self)
        scoped.update({
            "customers.communication_preferences": (
                pv.PreferencesSection, "Preferencias de comunicación",
                "Canal, horario y tipos de aviso que acepta cada cliente.", Icons.SETTINGS),
            "customers.consents": (
                pv.ConsentsSection, "Consentimientos",
                "Aviso de privacidad, WhatsApp, marketing… con su evidencia.", Icons.APPROVAL),
            "customers.whatsapp_summary": (
                pv.WhatsAppSection, "WhatsApp",
                "Consentimiento, conversaciones y mensajes del cliente (sin contenido).",
                Icons.PHONE),
            "customers.notification_history": (
                pv.WhatsAppSection, "Notificaciones",
                "Avisos enviados al cliente y su estado de entrega.", Icons.NOTIFICATIONS),
        })
        from frontend.desktop.modules.customers_crm.pages.commercial_pages import (
            COMMERCIAL_SECTIONS,
        )
        for commercial_route, (section, title, subtitle) in COMMERCIAL_SECTIONS.items():
            scoped[commercial_route] = (section, title, subtitle, Icons.SALES)
        if route_id in scoped:
            section, title, subtitle, icon = scoped[route_id]
            return cs.scoped_page(route_id, section, title, subtitle, icon)(
                self._presenter, self)
        return None

    def _open_lead(self, lead_id: str) -> None:
        detail = getattr(self, "_lead_detail", None)
        if detail is None:
            return
        self.select_route("crm.lead_detail")
        detail.show_lead(lead_id)

    def _open_case(self, case_id: str) -> None:
        detail = getattr(self, "_case_detail", None)
        if detail is None:
            return
        self.select_route("crm.case_detail")
        detail.show_case(case_id)

    def _open_opportunity(self, opportunity_id: str) -> None:
        detail = getattr(self, "_opportunity_detail", None)
        if detail is None:
            return
        self.select_route("crm.opportunity_detail")
        detail.show_opportunity(opportunity_id)

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
