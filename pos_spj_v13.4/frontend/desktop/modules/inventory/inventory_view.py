"""InventoryView (§54) — enterprise inventory shell with lateral navigation.

Composes a ``SideNav`` (the 21 canonical sections) with a ``QStackedWidget`` (one
page per section). Pages are built **lazily** on first navigation (light startup)
and each stack slot is a stable index container, so the section index always
matches its page index. If a page fails to build, its slot shows a notice instead
of crashing the module. Presentation-only — no SQL/business logic (the pages call
the presenter, which reaches the backend).
"""

from __future__ import annotations

import logging

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import SideNav

logger = logging.getLogger("spj.inventory.view")


class InventoryView(QWidget):
    def __init__(self, presenter, specs, parent=None) -> None:
        """``specs``: list of ``(page_factory, title)``. ``page_factory`` receives
        the presenter and returns a ``QWidget``."""
        super().__init__(parent)
        self.setObjectName("inventoryView")
        self._presenter = presenter
        self._specs = list(specs)
        self._built: dict[int, bool] = {}

        self.nav = SideNav()
        self.stack = QStackedWidget()
        for _factory, title in self._specs:
            self.nav.add_section(title)
            slot = QWidget()
            slot_layout = QVBoxLayout(slot)
            slot_layout.setContentsMargins(0, 0, 0, 0)
            self.stack.addWidget(slot)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)

        self.nav.navigated.connect(self._on_nav)
        if self._specs:
            self.nav.select(0)  # dispara la construcción de la primera sección

    def _on_nav(self, index: int) -> None:
        if not self._built.get(index):
            self._build_page(index)  # su __init__ hace el primer refresh
        else:
            self._refresh_page(index)  # revisitar re-lee datos (KPIs/tablas)
        self.stack.setCurrentIndex(index)

    def _refresh_page(self, index: int) -> None:
        container = self.stack.widget(index)
        page = (container.layout().itemAt(0).widget()
                if container.layout().count() else None)
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as exc:  # noqa: BLE001 — resiliencia como el host
                logger.error("Inventario: refresco de sección %d falló: %s", index, exc)

    def _build_page(self, index: int) -> None:
        factory, title = self._specs[index]
        container = self.stack.widget(index)
        try:
            page = factory(self._presenter)
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()  # primer llenado de datos al construir
        except Exception as exc:  # noqa: BLE001 — una página no debe tumbar el módulo
            logger.error("Inventario: falló la sección %s: %s", title, exc)
            page = QLabel(f"No disponible: {exc}")
        container.layout().addWidget(page)
        self._built[index] = True
