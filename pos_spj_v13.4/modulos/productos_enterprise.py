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
        # Sesión viva (con tiene_permiso) para el gating granular; None en tests.
        self._live_session = (getattr(container, "session", None)
                              or getattr(container, "sesion", None))

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
        from backend.application.products.authorization.permission_bridge import (
            SessionPermissionChecker,
            make_permission_checker,
        )
        from backend.application.products.authorization.policy import (
            ProductsAuthorizationPolicy,
        )
        from backend.application.products.queries.product_activation_readiness_query_service import (  # noqa: E501
            ProductActivationReadinessQueryService,
        )
        from backend.application.products.queries.unit_catalog_query_service import (
            UnitCatalogQueryService,
        )
        from backend.application.products.queries.product_code_query_service import (
            PreviewProductCodeQueryService,
        )
        from backend.application.products.use_cases.product_lifecycle_use_cases import (
            ActivateProductUseCase,
            SubmitProductUseCase,
        )
        from backend.application.products.queries.product_category_query_service import (
            ProductCategoryQueryService,
        )
        from backend.application.products.use_cases.product_category_use_cases import (
            CreateProductCategoryUseCase,
            MoveProductCategoryUseCase,
            SetProductCategoryActiveUseCase,
            UpdateProductCategoryUseCase,
        )
        from backend.application.products.queries.product_brand_query_service import (
            ProductBrandQueryService,
        )
        from backend.application.products.use_cases.product_brand_use_cases import (
            CreateProductBrandUseCase,
            SetProductBrandActiveUseCase,
            UpdateProductBrandUseCase,
        )
        from backend.application.products.queries.product_attribute_query_service import (
            ProductAttributeQueryService,
        )
        from backend.application.products.use_cases.product_attribute_use_cases import (
            AddAttributeOptionUseCase,
            CreateProductAttributeUseCase,
            SetProductAttributeActiveUseCase,
            UpdateAttributeOptionUseCase,
            UpdateProductAttributeUseCase,
        )
        from backend.application.products.queries.product_variant_query_service import (
            ProductVariantQueryService,
        )
        from backend.application.products.use_cases.product_variant_use_cases import (
            GenerateProductVariantsUseCase,
        )
        from backend.application.products.queries.product_image_query_service import (
            ProductImageQueryService,
        )
        from backend.application.products.use_cases.product_image_use_cases import (
            AddProductImageUseCase,
            RemoveProductImageUseCase,
            SetPrimaryImageUseCase,
        )
        from backend.application.products.queries.product_recipe_query_service import (
            ProductRecipeQueryService,
        )
        from backend.application.products.use_cases.product_recipe_use_cases import (
            ActivateRecipeVersionUseCase,
            ApproveRecipeVersionUseCase,
            CreateProductRecipeUseCase,
            SubmitRecipeVersionUseCase,
            UpdateDraftVersionUseCase,
        )
        from backend.application.products.queries.product_yield_query_service import (
            ProductYieldQueryService,
        )
        from backend.application.products.use_cases.product_yield_use_cases import (
            ActivateYieldVersionUseCase,
            ApproveYieldVersionUseCase,
            CreateYieldProfileUseCase,
            SubmitYieldVersionUseCase,
            UpdateYieldVersionUseCase,
        )
        from backend.application.products.queries.product_cutting_query_service import (
            ProductCuttingQueryService,
        )
        from backend.application.products.use_cases.product_cutting_use_cases import (
            ActivateCuttingVersionUseCase,
            ApproveCuttingVersionUseCase,
            CreateCuttingSchemeUseCase,
            SubmitCuttingVersionUseCase,
            UpdateCuttingVersionUseCase,
        )
        from frontend.desktop.modules.products.presenter import ProductsPresenter

        # P0-02: en producción la política SIEMPRE lleva un checker real (fail-closed);
        # sin sesión (tests de arranque) queda permisiva.
        authorization = (ProductsAuthorizationPolicy(
            SessionPermissionChecker(self._live_session))
            if self._live_session is not None else ProductsAuthorizationPolicy())

        def write_factory():
            return (CreateProductMasterUseCase(conn, authorization),
                    UpdateProductMasterUseCase(conn, authorization),
                    ProductMasterRepository(conn))

        def lifecycle_factory():
            return {
                "submit": SubmitProductUseCase(conn, authorization),
                "activate": ActivateProductUseCase(conn, authorization),
                "readiness": ProductActivationReadinessQueryService(conn),
            }

        def categories_write_factory():
            return {
                "create": CreateProductCategoryUseCase(conn, authorization),
                "update": UpdateProductCategoryUseCase(conn, authorization),
                "move": MoveProductCategoryUseCase(conn, authorization),
                "set_active": SetProductCategoryActiveUseCase(conn, authorization),
            }

        def brands_write_factory():
            return {
                "create": CreateProductBrandUseCase(conn, authorization),
                "update": UpdateProductBrandUseCase(conn, authorization),
                "set_active": SetProductBrandActiveUseCase(conn, authorization),
            }

        def attributes_write_factory():
            return {
                "create": CreateProductAttributeUseCase(conn, authorization),
                "update": UpdateProductAttributeUseCase(conn, authorization),
                "set_active": SetProductAttributeActiveUseCase(conn, authorization),
                "add_option": AddAttributeOptionUseCase(conn, authorization),
                "update_option": UpdateAttributeOptionUseCase(conn, authorization),
            }

        checker = (make_permission_checker(self._live_session)
                   if self._live_session is not None else None)
        return ProductsPresenter(
            read_service_factory=lambda: ProductCatalogReadService(conn),
            write_service_factory=write_factory,
            units_service_factory=lambda: UnitCatalogQueryService(conn),
            lifecycle_service_factory=lifecycle_factory,
            code_service_factory=lambda: PreviewProductCodeQueryService(conn),
            categories_read_factory=lambda: ProductCategoryQueryService(conn),
            categories_write_factory=categories_write_factory,
            brands_read_factory=lambda: ProductBrandQueryService(conn),
            brands_write_factory=brands_write_factory,
            attributes_read_factory=lambda: ProductAttributeQueryService(conn),
            attributes_write_factory=attributes_write_factory,
            variants_read_factory=lambda: ProductVariantQueryService(conn),
            variants_write_factory=lambda: GenerateProductVariantsUseCase(
                conn, authorization),
            images_read_factory=lambda: ProductImageQueryService(conn),
            images_write_factory=lambda: {
                "add": AddProductImageUseCase(conn, authorization),
                "set_primary": SetPrimaryImageUseCase(conn, authorization),
                "remove": RemoveProductImageUseCase(conn, authorization),
            },
            recipes_read_factory=lambda: ProductRecipeQueryService(conn),
            recipes_write_factory=lambda: {
                "create": CreateProductRecipeUseCase(conn, authorization),
                "update": UpdateDraftVersionUseCase(conn, authorization),
                "submit": SubmitRecipeVersionUseCase(conn, authorization),
                "approve": ApproveRecipeVersionUseCase(conn, authorization),
                "activate": ActivateRecipeVersionUseCase(conn, authorization),
            },
            yields_read_factory=lambda: ProductYieldQueryService(conn),
            yields_write_factory=lambda: {
                "create": CreateYieldProfileUseCase(conn, authorization),
                "update": UpdateYieldVersionUseCase(conn, authorization),
                "submit": SubmitYieldVersionUseCase(conn, authorization),
                "approve": ApproveYieldVersionUseCase(conn, authorization),
                "activate": ActivateYieldVersionUseCase(conn, authorization),
            },
            cutting_read_factory=lambda: ProductCuttingQueryService(conn),
            cutting_write_factory=lambda: {
                "create": CreateCuttingSchemeUseCase(conn, authorization),
                "update": UpdateCuttingVersionUseCase(conn, authorization),
                "submit": SubmitCuttingVersionUseCase(conn, authorization),
                "approve": ApproveCuttingVersionUseCase(conn, authorization),
                "activate": ActivateCuttingVersionUseCase(conn, authorization),
            },
            permission_checker=checker,
            session_context=session)

    def _add_pages(self, presenter):
        from frontend.desktop.modules.products.pages.overview_page import (
            ProductsOverviewPage,
        )
        from frontend.desktop.modules.products.pages.product_catalog_page import (
            ProductCatalogPage,
        )
        from frontend.desktop.modules.products.pages.categories_page import (
            ProductCategoriesPage,
        )
        from frontend.desktop.modules.products.pages.brands_page import (
            ProductBrandsPage,
        )
        from frontend.desktop.modules.products.pages.attributes_page import (
            ProductAttributesPage,
        )
        specs = (
            (ProductsOverviewPage, "Resumen"),
            (ProductCatalogPage, "Catálogo"),
            (ProductCategoriesPage, "Categorías"),
            (ProductBrandsPage, "Marcas"),
            (ProductAttributesPage, "Atributos"),
        )
        for cls, title in specs:
            try:
                self._tabs.addTab(cls(presenter), title)
            except Exception as exc:  # noqa: BLE001 — una página no debe tumbar el módulo
                logger.error("Productos enterprise: falló página %s: %s", title, exc)
                self._tabs.addTab(QLabel(f"No disponible: {exc}"), title)
