"""Contenedor del módulo de Precios y Costos.

POR QUÉ HACÍA FALTA ESCRIBIRLO
-------------------------------
El módulo tenía presentador, seis páginas, navegación declarativa y modelos de
vista — todo menos el widget que las junta. Sin él no había nada que el shell
pudiera abrir, así que registrarlo en el menú habría dado una entrada que no
lleva a ninguna parte.

Sigue la forma que `AssetsWorkspace` y `LossesView` ya usan: cabecera,
`SideNav` a la izquierda, `QStackedWidget` a la derecha, páginas construidas
PEREZOSAMENTE. Perezosamente importa de verdad: cada página consulta la base al
cargarse, y construirlas todas al abrir el módulo haría seis consultas para
enseñar una.

Sólo presentación. Ni SQL ni conexiones: todo pasa por `PricingPresenter`, que
a su vez llama al servicio de lectura de la capa de aplicación.
"""

from __future__ import annotations

from PyQt5.QtCore import QSignalBlocker
from PyQt5.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.pricing.navigation import visible_entries
from frontend.desktop.modules.pricing.routes import build_page
from frontend.desktop.themes.tokens import Spacing


class PricingWorkspace(QWidget):
    def __init__(self, presenter, parent=None, *, has_permission, page_builder=None) -> None:
        """`has_permission` es OBLIGATORIO y no tiene valor por omisión.

        La primera versión de este archivo lo deducía del presentador
        (`hasattr(presenter, "can")`) y, al no encontrarlo, caía en
        `lambda _c: True` — es decir, enseñaba las seis secciones a cualquiera.
        Un valor por omisión permisivo es exactamente lo que §23 prohíbe: el
        fallo no se ve, porque la pantalla funciona.
        """
        super().__init__(parent)
        self._presenter = presenter
        self._has_permission = has_permission
        self._page_builder = page_builder or build_page
        self._pages: dict[str, QWidget] = {}
        self._index_by_page_id: dict[str, int] = {}
        self.setObjectName("pricingWorkspace")
        self.setAccessibleName("Módulo de Precios y Costos")

        root = QVBoxLayout(self)
        root.setContentsMargins(
            Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL,
            Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL)
        root.setSpacing(Spacing.MD)

        root.addWidget(PageHeader(
            self, title="Precios y Costos",
            subtitle="Listas de precio, precios por producto, costos e historial.",
            icon=Icons.FINANCE, compact=True))

        shell = QHBoxLayout()
        shell.setSpacing(Spacing.LG)
        root.addLayout(shell, stretch=1)

        self._nav = SideNav(self)
        self._nav.setProperty("role", "nav")
        self._nav.setAccessibleName("Navegación de Precios y Costos")
        self._nav.navigated.connect(self._on_navigated)
        shell.addWidget(self._nav)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("pricingStack")
        self._stack.setAccessibleName("Páginas del módulo de Precios y Costos")
        self.viewport = PageViewport(self)
        self.viewport.set_page(self._stack)
        shell.addWidget(self.viewport, stretch=1)

        self._build_routes()

    # ── construcción ─────────────────────────────────────────────────────
    def _build_routes(self) -> None:
        """Sólo las secciones que la sesión puede ver.

        Ocultar es UX, no seguridad —el backend revalida cada acción— pero
        enseñar una sección que al abrirse va a denegar es peor que no
        enseñarla.
        """
        entradas = visible_entries(self._has_permission)

        if not entradas:
            # Sin ni una sección visible el módulo no puede quedar en blanco: un
            # panel vacío sin explicación se lee como una pantalla rota.
            self._stack.addWidget(create_state_widget(
                ViewState.EMPTY,
                message="No tiene permisos para ver ninguna sección de Precios."))
            return

        for fila, entrada in enumerate(entradas):
            self._nav.add_section(entrada.title, entrada.icon)
            item = self._nav.item(fila)
            if item is not None:
                item.setToolTip(entrada.tooltip)
            marcador = create_state_widget(ViewState.LOADING, message=entrada.title)
            self._index_by_page_id[entrada.page_id] = self._stack.addWidget(marcador)

        self.select_page(entradas[0].page_id)

    # ── navegación ───────────────────────────────────────────────────────
    def _on_navigated(self, fila: int) -> None:
        for page_id, indice in self._index_by_page_id.items():
            if indice == fila:
                self.select_page(page_id)
                return

    def select_page(self, page_id: str) -> None:
        indice = self._index_by_page_id.get(page_id)
        if indice is None:
            return
        pagina = self._pages.get(page_id)
        if pagina is None:
            pagina = self._page_builder(page_id, self._presenter)
            if pagina is None:
                # Una sección declarada sin página construida todavía: estado
                # vacío explícito, nunca `None` — el apilado no acepta huecos y
                # un hueco silencioso deja la pantalla anterior a la vista,
                # como si la navegación no hubiera hecho nada.
                pagina = create_state_widget(
                    ViewState.EMPTY, message="Esta sección aún no está construida.")
            self._pages[page_id] = pagina
            marcador = self._stack.widget(indice)
            self._stack.removeWidget(marcador)
            marcador.deleteLater()
            self._stack.insertWidget(indice, pagina)
            self._index_by_page_id[page_id] = self._stack.indexOf(pagina)
            indice = self._index_by_page_id[page_id]

        self._stack.setCurrentIndex(indice)
        with QSignalBlocker(self._nav):
            self._nav.select(indice)
        cargar = getattr(pagina, "ensure_loaded", None)
        if callable(cargar):
            cargar()

    @property
    def active_page_id(self) -> str:
        actual = self._stack.currentIndex()
        for page_id, indice in self._index_by_page_id.items():
            if indice == actual:
                return page_id
        return ""
