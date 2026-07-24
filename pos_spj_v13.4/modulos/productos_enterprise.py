"""ModuloProductosEnterprise — PROD-19 FLIP: reemplazo de la UI legacy de Productos
(modulos/productos.py) por el módulo enterprise PRC-7 (frontend/desktop/modules/
products).

Monta las páginas born-clean (Resumen + Catálogo) sobre ProductsPresenter, cableado
al read service canónico ProductCatalogReadService (maestro `products`). Sin SQL ni
lógica de negocio en la UI.

NOTA (decisión del usuario, corte "borrar ya"): las páginas de alta/edición de
producto aún no están migradas; este host es de sólo lectura. El alta/edición se
reincorporará cuando se construyan los formularios enterprise (los use cases
canónicos CreateProductUseCase/UpdateProductUseCase ya existen).
"""

from __future__ import annotations

import logging

from PyQt5.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

logger = logging.getLogger("spj.ui.productos_enterprise")


class _Session:
    def __init__(self, user_id, branch_id):
        self.user_id = user_id
        self.branch_id = branch_id


class ModuloProductosEnterprise(QWidget):
    """Contenedor PyQt5 del módulo Productos enterprise (PRC-7) para el shell del POS."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        conn = getattr(container, "db", container)
        user_id = (getattr(container, "usuario", None)
                   or getattr(container, "usuario_actual", None) or "desktop")
        branch_id = str(getattr(container, "sucursal_id", None)
                        or getattr(container, "branch_id", None) or "1")
        session = _Session(user_id, branch_id)

        presenter = self._build_presenter(conn, session)
        self._tabs = QTabWidget()
        self._add_pages(presenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

    def _build_presenter(self, conn, session):
        from backend.application.products.queries.catalog_read_service import (
            ProductCatalogReadService,
        )
        from backend.application.products.use_cases.product_master_use_cases import (
            CreateProductMasterUseCase,
            UpdateProductMasterUseCase,
        )
        from backend.infrastructure.db.repositories.products.product_master_repository import (
            ProductMasterRepository,
        )
        from frontend.desktop.modules.products.presenter import ProductsPresenter

        def write_factory():
            return (CreateProductMasterUseCase(conn), UpdateProductMasterUseCase(conn),
                    ProductMasterRepository(conn))

        return ProductsPresenter(
            read_service_factory=lambda: ProductCatalogReadService(conn),
            write_service_factory=write_factory,
            session_context=session)

    def _add_pages(self, presenter):
        from frontend.desktop.modules.products.pages.overview_page import (
            ProductsOverviewPage,
        )
        from frontend.desktop.modules.products.pages.product_catalog_page import (
            ProductCatalogPage,
        )
        specs = (
            (ProductsOverviewPage, "Resumen"),
            (ProductCatalogPage, "Catálogo"),
        )
        for cls, title in specs:
            try:
                self._tabs.addTab(cls(presenter), title)
            except Exception as exc:  # noqa: BLE001 — una página no debe tumbar el módulo
                logger.error("Productos enterprise: falló página %s: %s", title, exc)
                self._tabs.addTab(QLabel(f"No disponible: {exc}"), title)
