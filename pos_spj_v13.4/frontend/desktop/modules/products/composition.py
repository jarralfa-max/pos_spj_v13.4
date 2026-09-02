"""Composition root for the Products desktop module — SHELL-16 extraction.

Extracted verbatim (only `conn`→`connection` renamed for consistency with
`sales_pos`/`customers_crm`/`finance`/`hr`/`inventory`'s own composition
roots) from `modulos/productos_enterprise.py::ModuloProductosEnterprise._build_presenter`/
`_build_view`, where this logic used to live. Behavior is preserved
exactly; the existing regression tests
(`tests/integration/products/test_products_enterprise_host.py`) were
written against the old location and still pass unmodified, since
`modulos/productos_enterprise.py` now just calls through to this file.

Two identity inputs, kept deliberately separate exactly as the original
did:
- `live_session`: the raw `container.session` (or `None`) — read live on
  every property access via `_Session` below, and used directly for the
  authorization checker (`SessionPermissionChecker`/`make_permission_checker`
  need the real session object, not the wrapper).
- `session_context`: an already-built `_Session` instance wrapping
  `live_session` plus a `branch_id_fallback` (from `container.sucursal_id`/
  `container.branch_id` — a *different* container attribute than
  `.session`) — this is what `ProductsPresenter` actually receives as
  `session_context`.

Takes only plain arguments — a bare `connection` plus those two identity
inputs — never the app's whole dependency container. The outer unwrapping
step stays in `modulos/productos_enterprise.py`, mirroring
`modulos/ventas_pos.py`'s own split for `sales_pos`.
"""
from __future__ import annotations


class _Session:
    """Vista de identidad para las mutaciones (ciclo de vida, recetas, etc.).

    Lee SIEMPRE EN VIVO desde la sesión real (`SessionContext`) — nunca una foto
    fija tomada al construir el widget. `MainWindow._construir_todas_las_pantallas()`
    construye todos los módulos (incluido este) dentro de `__init__`, ANTES de que
    el usuario inicie sesión (el login se dispara después, vía
    `QTimer.singleShot(0, self.mostrar_login)` en `MainWindow.showEvent`); una foto
    fija de `user_id` tomada en ese momento queda vacía para siempre, aunque el
    usuario inicie sesión un instante después (bug real reportado en producción:
    "Operación sin usuario autenticado" al activar un producto pese a haber una
    sesión autenticada). `container.session` es un singleton mutado en el lugar
    (`set_permisos`/`iniciar_sesion`/`set_sucursal`, nunca reasignado), así que
    guardar la referencia y leer sus properties en cada acceso es correcto y
    suficiente — no hace falta re-consultar `container` cada vez.
    """

    def __init__(self, live_session, branch_id_fallback: str | None = None) -> None:
        self._live = live_session
        self._branch_fallback = branch_id_fallback

    @property
    def user_id(self) -> str | None:
        return getattr(self._live, "user_id", None) or None

    @property
    def branch_id(self) -> str | None:
        value = getattr(self._live, "sucursal_id", None)
        return str(value) if value else self._branch_fallback


def build_products_presenter(connection, session_context=None, *, live_session=None):
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
    from backend.application.products.queries.product_bundle_query_service import (
        ProductBundleQueryService,
    )
    from backend.application.products.use_cases.product_bundle_use_cases import (
        ActivateBundleVersionUseCase,
        ApproveBundleVersionUseCase,
        CreateProductBundleUseCase,
        SubmitBundleVersionUseCase,
        UpdateBundleVersionUseCase,
    )
    from backend.application.products.queries.product_import_query_service import (
        ProductImportQueryService,
    )
    from backend.application.products.queries.species_catalog_query_service import (
        SpeciesCatalogQueryService,
    )
    from backend.application.products.queries.branch_assortment_query_service import (
        BranchAssortmentQueryService,
    )
    from backend.application.products.use_cases.product_branch_assortment_use_cases import (
        CreateAssortmentUseCase,
        SetAssortmentProductUseCase,
        SetBranchProductUseCase,
    )
    from backend.application.products.use_cases.product_import_use_cases import (
        ApproveImportBatchUseCase,
        CreateImportBatchUseCase,
        ExecuteImportBatchUseCase,
    )
    from frontend.desktop.modules.products.presenter import ProductsPresenter

    conn = connection

    # P0-02: en producción la política SIEMPRE lleva un checker real (fail-closed);
    # sin sesión (tests de arranque) queda permisiva.
    # §21.1 fail-closed: con sesión viva se cablea el checker real; sin sesión
    # (arranque/tests o shell de sólo lectura) se usa la política permisiva
    # EXPLÍCITA de pruebas — nunca el permisivo silencioso.
    authorization = (ProductsAuthorizationPolicy(
        SessionPermissionChecker(live_session))
        if live_session is not None
        else ProductsAuthorizationPolicy.permissive_for_tests())

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
            "edit": UpdateProductCategoryUseCase(conn, authorization),
            "move": MoveProductCategoryUseCase(conn, authorization),
            "set_active": SetProductCategoryActiveUseCase(conn, authorization),
        }

    def brands_write_factory():
        return {
            "create": CreateProductBrandUseCase(conn, authorization),
            "edit": UpdateProductBrandUseCase(conn, authorization),
            "set_active": SetProductBrandActiveUseCase(conn, authorization),
        }

    def attributes_write_factory():
        return {
            "create": CreateProductAttributeUseCase(conn, authorization),
            "edit": UpdateProductAttributeUseCase(conn, authorization),
            "set_active": SetProductAttributeActiveUseCase(conn, authorization),
            "add_option": AddAttributeOptionUseCase(conn, authorization),
            "update_option": UpdateAttributeOptionUseCase(conn, authorization),
        }

    checker = (make_permission_checker(live_session)
               if live_session is not None else None)
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
            "edit": UpdateDraftVersionUseCase(conn, authorization),
            "submit": SubmitRecipeVersionUseCase(conn, authorization),
            "approve": ApproveRecipeVersionUseCase(conn, authorization),
            "activate": ActivateRecipeVersionUseCase(conn, authorization),
        },
        yields_read_factory=lambda: ProductYieldQueryService(conn),
        yields_write_factory=lambda: {
            "create": CreateYieldProfileUseCase(conn, authorization),
            "edit": UpdateYieldVersionUseCase(conn, authorization),
            "submit": SubmitYieldVersionUseCase(conn, authorization),
            "approve": ApproveYieldVersionUseCase(conn, authorization),
            "activate": ActivateYieldVersionUseCase(conn, authorization),
        },
        cutting_read_factory=lambda: ProductCuttingQueryService(conn),
        cutting_write_factory=lambda: {
            "create": CreateCuttingSchemeUseCase(conn, authorization),
            "edit": UpdateCuttingVersionUseCase(conn, authorization),
            "submit": SubmitCuttingVersionUseCase(conn, authorization),
            "approve": ApproveCuttingVersionUseCase(conn, authorization),
            "activate": ActivateCuttingVersionUseCase(conn, authorization),
        },
        bundles_read_factory=lambda: ProductBundleQueryService(conn),
        bundles_write_factory=lambda: {
            "create": CreateProductBundleUseCase(conn, authorization),
            "edit": UpdateBundleVersionUseCase(conn, authorization),
            "submit": SubmitBundleVersionUseCase(conn, authorization),
            "approve": ApproveBundleVersionUseCase(conn, authorization),
            "activate": ActivateBundleVersionUseCase(conn, authorization),
        },
        import_read_factory=lambda: ProductImportQueryService(conn),
        import_write_factory=lambda: {
            "create": CreateImportBatchUseCase(conn, authorization),
            "approve": ApproveImportBatchUseCase(conn, authorization),
            "execute": ExecuteImportBatchUseCase(conn, authorization),
        },
        species_read_factory=lambda: SpeciesCatalogQueryService(conn),
        branch_read_factory=lambda: BranchAssortmentQueryService(conn),
        branch_write_factory=lambda: {
            "branch": SetBranchProductUseCase(conn, authorization),
            "create_assortment": CreateAssortmentUseCase(conn, authorization),
            "set_assortment_product": SetAssortmentProductUseCase(conn, authorization),
        },
        permission_checker=checker,
        session_context=session_context)


def build_products_view(presenter, parent=None):
    """Shell enterprise con navegación lateral (SideNav + páginas apiladas).

    Las páginas se construyen de forma perezosa al navegar (arranque liviano) y
    cada sección es resiliente a fallos de su propia página (ver ProductsView)."""
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
    from frontend.desktop.modules.products.pages.import_page import (
        ProductImportPage,
    )
    from frontend.desktop.modules.products.pages.branch_channel_page import (
        BranchChannelPage,
    )
    from frontend.desktop.modules.products.products_view import ProductsView

    specs = (
        (ProductsOverviewPage, "Resumen"),
        (ProductCatalogPage, "Catálogo"),
        (ProductCategoriesPage, "Categorías"),
        (ProductBrandsPage, "Marcas"),
        (ProductAttributesPage, "Atributos"),
        (BranchChannelPage, "Sucursales y canales"),
        (ProductImportPage, "Importar"),
    )
    return ProductsView(presenter, specs, parent)


def create_products_view(connection, session_context=None, *, live_session=None, parent=None):
    """Factory used by `modulos/productos_enterprise.py`. Never receives
    the container itself — only what it needs, already unwrapped."""
    presenter = build_products_presenter(connection, session_context, live_session=live_session)
    return build_products_view(presenter, parent)
