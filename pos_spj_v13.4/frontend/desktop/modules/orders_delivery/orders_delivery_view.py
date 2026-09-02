"""Enterprise Pedidos y Delivery workspace with persistent permission-aware
sidebar. Mirrors
`frontend/desktop/modules/losses/losses_view.py::LossesView` exactly.

Not wired into `interfaz/menu_lateral.py`/`main_window.py`/`core/app_container.py`
yet — that cutover is a separate, larger decision (this module coexists as an
additional entry point alongside the live `modulos/delivery.py`, same pattern
already established for Configuración "(Nuevo)", see
`docs/refactor/module_relocation_map.md`). ORD-4 only builds the navigable
skeleton and its tests.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from frontend.desktop.modules.orders_delivery.orders_delivery_routes import build_page
from frontend.desktop.modules.orders_delivery.widgets import OrdersDeliverySidebarWidget
from frontend.desktop.themes.tokens import ResponsiveBreakpoints


class OrdersDeliveryView(QWidget):
    def __init__(self, *, has_permission, badges=None, page_builder=None, parent=None,
                 connection=None, branch_id: str | None = None,
                 actor_user_id: str | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ordersDeliveryModule")
        self.setAccessibleName("Módulo de Pedidos y Delivery")
        self.setAccessibleDescription(
            "Espacio de trabajo para capturar, preparar y entregar pedidos."
        )
        self.setMinimumSize(640, 480)
        if page_builder is not None:
            self._page_builder = page_builder
        else:
            # ORD-28: when a real `connection` is supplied, real pages
            # (Resumen/Todos los pedidos/Análisis) render instead of the
            # ORD-4 placeholder — see `orders_delivery_routes.build_page`'s
            # own `_REAL_ROUTE_BUILDERS`. No connection (the default,
            # matching every existing caller/test) keeps the exact ORD-4
            # placeholder-only behavior.
            self._page_builder = lambda page_id: build_page(
                page_id, connection, branch_id=branch_id, actor_user_id=actor_user_id)
        self._pages = {}
        self._active_route = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = OrdersDeliverySidebarWidget(
            has_permission=has_permission, badges=badges, parent=self)
        self.stack = QStackedWidget(self)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, stretch=1)
        self.sidebar.route_requested.connect(self.show_route)
        if self.sidebar.count():
            self.show_route(str(self.sidebar.item(0).data(Qt.UserRole)))

    def resizeEvent(self, event):  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self.apply_responsive_layout()

    def apply_responsive_layout(self) -> None:
        """Keep navigation usable at supported compact desktop widths."""
        self.sidebar.set_collapsed(self.width() < ResponsiveBreakpoints.COMPACT)

    @property
    def active_route(self):
        return self._active_route

    def show_route(self, page_id: str) -> None:
        page = self._pages.get(page_id)
        if page is None:
            page = self._page_builder(page_id)
            self._pages[page_id] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self._active_route = page_id
        entry = next(
            (self.sidebar.item(row) for row in range(self.sidebar.count())
             if self.sidebar.item(row).data(Qt.UserRole) == page_id),
            None,
        )
        if entry is not None and self.sidebar.currentItem() is not entry:
            previous = self.sidebar.blockSignals(True)
            self.sidebar.setCurrentItem(entry)
            self.sidebar.blockSignals(previous)
        ensure_loaded = getattr(page, "ensure_loaded", None)
        if callable(ensure_loaded):
            ensure_loaded()
