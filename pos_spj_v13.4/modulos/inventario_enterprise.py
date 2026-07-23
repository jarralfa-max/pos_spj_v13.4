"""ModuloInventarioEnterprise — INV-27 corte: reemplazo de la UI legacy de
inventario (modulos/inventario_local.py) por el módulo enterprise INV-25.

Monta las páginas born-clean (frontend/desktop/modules/inventory) sobre el
InventoryPresenter, cableado a los query services canónicos (ledger). Sin SQL ni
lógica de negocio en la UI.

La página de Analítica usa HtmlChartView (QtWebEngine) que se cuelga bajo
offscreen headless, por eso se construye de forma perezosa al abrir su pestaña.
"""

from __future__ import annotations

import logging

from PyQt5.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

logger = logging.getLogger("spj.ui.inventario_enterprise")


class _Session:
    def __init__(self, user_id, branch_id, warehouse_id):
        self.user_id = user_id
        self.branch_id = branch_id
        self.warehouse_id = warehouse_id


class ModuloInventarioEnterprise(QWidget):
    """Contenedor PyQt5 del inventario enterprise (INV-25) para el shell del POS."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        conn = getattr(container, "db", container)
        user_id = (getattr(container, "usuario", None)
                   or getattr(container, "usuario_actual", None) or "desktop")
        branch_id = str(getattr(container, "sucursal_id", None)
                        or getattr(container, "branch_id", None) or "1")
        session = _Session(user_id, branch_id, branch_id)

        presenter = self._build_presenter(conn, session)
        self._tabs = QTabWidget()
        self._presenter = presenter
        self._analytics_built = False

        self._add_eager_pages(presenter)
        # Analítica: pestaña perezosa (QtWebEngine).
        self._analytics_index = self._tabs.addTab(QWidget(), "Analítica")
        self._tabs.currentChanged.connect(self._maybe_build_analytics)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

    # ── construcción ─────────────────────────────────────────────────────────
    def _build_presenter(self, conn, session):
        from backend.application.inventory.analytics import InventoryAnalyticsService
        from backend.application.inventory.queries import (
            InventoryAvailabilityQueryService,
            ReplenishmentQueryService,
            WarehouseQueryService,
        )
        from backend.application.inventory.use_cases import (
            GenerateReplenishmentSuggestionsUseCase,
        )
        from frontend.desktop.modules.inventory.presenter import InventoryPresenter

        return InventoryPresenter(
            connection_provider=lambda: conn,
            availability_service_factory=InventoryAvailabilityQueryService,
            replenishment_query_factory=ReplenishmentQueryService,
            generate_suggestions_uc=GenerateReplenishmentSuggestionsUseCase(),
            warehouse_query_factory=WarehouseQueryService,
            analytics_factory=InventoryAnalyticsService,
            session_context=session,
        )

    def _add_eager_pages(self, presenter):
        from frontend.desktop.modules.inventory.pages import (
            InventoryDashboardPage,
            LocationsPage,
            ReplenishmentPage,
            WarehousesPage,
        )
        specs = (
            (InventoryDashboardPage, "Panel", {}),
            (WarehousesPage, "Almacenes", {}),
            (LocationsPage, "Ubicaciones", {}),
            (ReplenishmentPage, "Reposición", {}),
        )
        for cls, title, kwargs in specs:
            try:
                self._tabs.addTab(cls(presenter, **kwargs), title)
            except Exception as exc:  # noqa: BLE001 — una página no debe tumbar el módulo
                logger.error("Inventario enterprise: falló página %s: %s", title, exc)
                self._tabs.addTab(QLabel(f"No disponible: {exc}"), title)

    def _maybe_build_analytics(self, index):
        if index != self._analytics_index or self._analytics_built:
            return
        self._analytics_built = True
        try:
            from frontend.desktop.modules.inventory.pages import InventoryAnalyticsPage
            page = InventoryAnalyticsPage(self._presenter)
        except Exception as exc:  # noqa: BLE001
            logger.error("Inventario enterprise: falló Analítica: %s", exc)
            page = QLabel(f"Analítica no disponible: {exc}")
        self._tabs.removeTab(self._analytics_index)
        self._tabs.insertTab(self._analytics_index, page, "Analítica")
        self._tabs.setCurrentIndex(self._analytics_index)
