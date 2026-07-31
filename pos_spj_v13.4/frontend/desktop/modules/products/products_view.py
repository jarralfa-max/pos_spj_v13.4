"""ProductsView — shell enterprise del módulo Productos con navegación lateral.

Compone un ``SideNav`` (secciones) con un ``QStackedWidget`` (páginas). Las páginas
se construyen **de forma perezosa** al navegar por primera vez (arranque liviano) y
cada slot es un contenedor de índice estable, de modo que el índice de la sección
siempre coincide con el de su página. Si una página falla al construirse, su slot
muestra un aviso en vez de tumbar el módulo (resiliencia como el host anterior).
"""

from __future__ import annotations

import logging

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import SideNav

logger = logging.getLogger("spj.products.view")


class ProductsView(QWidget):
    #: §8.3/§3.3 — señal central: una página que muta productos la emite; las
    #: páginas que muestran datos (KPIs, catálogo) la conectan a su refresh, para
    #: reflejar cambios sin navegar.
    product_data_changed = pyqtSignal()

    def __init__(self, presenter, specs, parent=None) -> None:
        """``specs``: lista de ``(page_factory, título)``. ``page_factory`` recibe el
        presenter y devuelve un ``QWidget``."""
        super().__init__(parent)
        self.setObjectName("productsView")
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
            self._build_page(index)  # su __init__ ya hace el primer refresh
        else:
            self._refresh_page(index)  # §3.3/§8.3: revisitar re-lee los datos (KPIs)
        self.stack.setCurrentIndex(index)

    def _refresh_page(self, index: int) -> None:
        """Refresca la página ya construida al re-navegar, para que los KPIs y
        tablas reflejen mutaciones hechas en otras páginas (sin reiniciar la app).
        Una falla de refresco no debe tumbar la navegación."""
        container = self.stack.widget(index)
        page = container.layout().itemAt(0).widget() if container.layout().count() else None
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as exc:  # noqa: BLE001 — resiliencia como el host
                logger.error("Productos: refresco de sección %d falló: %s", index, exc)

    def _build_page(self, index: int) -> None:
        factory, title = self._specs[index]
        container = self.stack.widget(index)
        try:
            page = factory(self._presenter)
        except Exception as exc:  # noqa: BLE001 — una página no debe tumbar el módulo
            logger.error("Productos: falló la sección %s: %s", title, exc)
            page = QLabel(f"No disponible: {exc}")
        container.layout().addWidget(page)
        self._built[index] = True
        # §8.3: cablea la señal central en la página recién construida.
        connect = getattr(page, "set_data_changed_signal", None)
        if callable(connect):
            try:
                connect(self.product_data_changed)
            except Exception as exc:  # noqa: BLE001 — no debe romper la construcción
                logger.error("Productos: no se pudo cablear la señal en %s: %s",
                             self._specs[index][1], exc)
