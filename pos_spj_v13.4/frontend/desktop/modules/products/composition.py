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


def build_products_presenter(connection, session_context=None, *, live_session=None,
                             external_registry=None):
    from backend.application.products.queries.integration_query_services import (
        PurchaseProductConfigQueryService,
    )
    from backend.application.products.use_cases.product_unit_use_cases import (
        CreateUnitConversionUseCase,
        SetConversionFractionalReceiptUseCase,
        SetUnitConversionActiveUseCase,
    )
    from backend.application.products.queries.catalog_read_service import (
        ProductCatalogReadService,
    )
    from backend.application.products.queries.product_selection_query_service import (
        ProductCatalogSearchQueryService,
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
        RemoveImageBackgroundUseCase,
        RemoveProductImageUseCase,
        RestoreImageBackgroundUseCase,
        SetPrimaryImageUseCase,
    )
    from backend.infrastructure.media.background_removal import (
        EdgeConnectedBackgroundRemover,
    )
    from backend.infrastructure.media.local_product_image_storage import (
        LocalProductImageStorage,
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
        SetCuttingReverseReconstructionUseCase,
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
    # PROD-21: las imágenes se copian a la carpeta de la aplicación.
    image_storage = LocalProductImageStorage()

    def write_factory():
        # PROD-22: las alertas del §35 se leen de Productos → Configuración en
        # cada alta/edición (apagadas por omisión, como hasta ahora).
        alerts = _alert_wiring(conn)
        return (CreateProductMasterUseCase(conn, authorization, **alerts),
                UpdateProductMasterUseCase(conn, authorization, **alerts),
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
    presenter = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        # El SELECTOR de productos va por el contrato compartido; el listado
        # del catálogo sigue en `ProductCatalogReadService`.
        product_search_factory=lambda: ProductCatalogSearchQueryService(conn),
        write_service_factory=write_factory,
        units_service_factory=lambda: UnitCatalogQueryService(conn),
        units_write_factory=lambda: {
            "create_conversion": CreateUnitConversionUseCase(conn, authorization),
            "set_conversion_active": SetUnitConversionActiveUseCase(conn, authorization),
            "set_conversion_fractional": SetConversionFractionalReceiptUseCase(
                conn, authorization),
        },
        purchase_config_factory=lambda: PurchaseProductConfigQueryService(conn),
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
            "add": AddProductImageUseCase(conn, authorization, image_storage),
            "set_primary": SetPrimaryImageUseCase(conn, authorization),
            "remove": RemoveProductImageUseCase(conn, authorization, image_storage),
            "remove_background": RemoveImageBackgroundUseCase(
                conn, authorization, image_storage, EdgeConnectedBackgroundRemover()),
            "restore_background": RestoreImageBackgroundUseCase(
                conn, authorization, image_storage),
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
            # §16: armar el producto con sus partes (Fase 7).
            "reverse": SetCuttingReverseReconstructionUseCase(conn, authorization),
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
    # PROD-22: clasificación cárnica (especies, regiones, cortes). El backend
    # existía completo y ninguna pantalla lo alcanzaba.
    presenter.meat = _build_meat_presenter(conn, authorization, checker, session_context)
    # PROD-22: códigos de barras y perfiles (calidad/vida útil/logística) de UN
    # producto — acciones del expediente, sin pantalla hasta ahora.
    presenter.codes_profiles = _build_codes_profiles_presenter(
        conn, authorization, checker, session_context)
    # PROD-22 §40: la bitácora existía sin pantalla para consultarla.
    from backend.application.products.queries.product_audit_query_service import (
        ProductAuditQueryService,
    )
    from frontend.desktop.modules.products.audit_presenter import ProductAuditPresenter
    presenter.audit = ProductAuditPresenter(
        read_factory=lambda: ProductAuditQueryService(conn), has_permission=checker)
    # PROD-22: bandeja transversal de versiones técnicas pendientes.
    from backend.application.products.queries.product_approval_query_service import (
        ProductApprovalQueryService,
    )
    presenter.approvals = ProductApprovalQueryService(conn)
    # PROD-22 §35/§42: calidad de datos con las reglas de las alertas.
    from backend.application.products.queries.product_data_quality_query_service import (
        ProductDataQualityQueryService,
    )
    presenter.data_quality = ProductDataQualityQueryService(conn)
    presenter.external = _build_external_presenter(conn, authorization, checker,
                                                   session_context, external_registry)
    presenter.settings = _build_settings_presenter(conn, authorization, checker,
                                                   session_context)
    return presenter


def _build_external_presenter(conn, authorization, checker, session_context, registry):
    """Catálogo externo (§15). El registro de proveedores se crea al usarse (la
    búsqueda sale a internet); los tests inyectan uno falso."""
    from backend.application.products.queries.external_catalog_query_service import (
        ExternalCatalogQueryService,
    )
    from backend.application.products.use_cases.product_external_catalog_use_cases import (
        ApproveExternalRecordUseCase,
        ImportExternalRecordUseCase,
        RejectExternalRecordUseCase,
        SearchExternalCatalogUseCase,
    )
    from frontend.desktop.modules.products.external_catalog_presenter import (
        ExternalCatalogPresenter,
    )

    def write_factory():
        reg = registry
        if reg is None:
            from backend.infrastructure.product_catalogs.catalog_wiring import (
                build_default_registry,
            )
            reg = build_default_registry()
        return {"search": SearchExternalCatalogUseCase(conn, reg, authorization),
                "approve": ApproveExternalRecordUseCase(conn, reg, authorization),
                "reject": RejectExternalRecordUseCase(conn, reg, authorization),
                "import": ImportExternalRecordUseCase(conn, reg, authorization)}

    return ExternalCatalogPresenter(
        read_factory=lambda: ExternalCatalogQueryService(conn), write_factory=write_factory,
        has_permission=checker, session=session_context)


def _alert_wiring(conn) -> dict:
    """Servicio + destinatarios de las alertas, según la configuración vigente."""
    from backend.application.products.notifications.notification_service import (
        ProductNotificationService,
    )
    from backend.application.products.queries.product_settings_query import (
        ProductSettingsQuery,
    )
    from backend.infrastructure.notifications.product_notification_gateway import (
        FanOutProductNotificationGateway,
    )
    try:
        query = ProductSettingsQuery(conn)
        settings = query.current()
    except Exception:  # sin catálogo de ajustes: sin alertas
        return {}
    if not settings.alerts_enabled:
        return {}
    phones = list(settings.whatsapp_phones) if settings.whatsapp_enabled else []
    return {"notification_service": ProductNotificationService(
                conn, gateway=FanOutProductNotificationGateway(conn)),
            "notify_recipients": query.alert_user_ids(settings),
            "whatsapp_recipients": phones}


def _build_settings_presenter(conn, authorization, checker, session_context):
    from backend.application.products.queries.product_notification_log_query import (
        ProductNotificationLogQuery,
    )
    from backend.application.products.queries.product_settings_query import (
        ProductSettingsQuery,
    )
    from backend.application.products.use_cases.product_settings_use_cases import (
        UpdateProductSettingsUseCase,
    )
    from frontend.desktop.modules.products.settings_presenter import ProductSettingsPresenter
    from backend.application.products.notifications.whatsapp_outbox import (
        ProductWhatsAppOutboxQuery,
        RetryProductWhatsAppMessageUseCase,
    )
    return ProductSettingsPresenter(
        read_factory=lambda: ProductSettingsQuery(conn),
        write_factory=lambda: UpdateProductSettingsUseCase(conn, authorization),
        log_factory=lambda: ProductNotificationLogQuery(conn),
        outbox_factory=lambda: ProductWhatsAppOutboxQuery(conn),
        retry_factory=lambda: RetryProductWhatsAppMessageUseCase(conn, authorization),
        has_permission=checker, session=session_context)


def _build_codes_profiles_presenter(conn, authorization, checker, session_context):
    from backend.application.products.queries.product_barcode_query_service import (
        ProductBarcodeQueryService,
    )
    from backend.application.products.queries.product_profile_query_service import (
        ProductProfileQueryService,
    )
    from backend.application.products.use_cases.product_barcode_use_cases import (
        AddAlternateCodeUseCase,
        AssignBarcodeUseCase,
        SetBarcodeActiveUseCase,
    )
    from backend.application.products.use_cases.product_profile_use_cases import (
        SetLogisticsProfileUseCase,
        SetQualityProfileUseCase,
        SetShelfLifeProfileUseCase,
    )
    from frontend.desktop.modules.products.product_codes_profiles_presenter import (
        ProductCodesProfilesPresenter,
    )
    return ProductCodesProfilesPresenter(
        read_factory=lambda: (ProductBarcodeQueryService(conn),
                              ProductProfileQueryService(conn)),
        write_factory=lambda: {
            "assign_barcode": AssignBarcodeUseCase(conn, authorization),
            "set_barcode_active": SetBarcodeActiveUseCase(conn, authorization),
            "add_alternate_code": AddAlternateCodeUseCase(conn, authorization),
            "shelf_life": SetShelfLifeProfileUseCase(conn, authorization),
            "quality": SetQualityProfileUseCase(conn, authorization),
            "logistics": SetLogisticsProfileUseCase(conn, authorization),
        },
        has_permission=checker, session=session_context)


def _build_meat_presenter(conn, authorization, checker, session_context):
    from backend.application.products.queries.meat_classification_query_service import (
        MeatClassificationQueryService,
    )
    from backend.application.products.queries.species_catalog_query_service import (
        SpeciesCatalogQueryService,
    )
    from backend.application.products.queries.product_profile_query_service import (
        ProductProfileQueryService,
    )
    from backend.application.products.queries.unit_catalog_query_service import (
        UnitCatalogQueryService,
    )
    from backend.application.products.use_cases.product_unit_use_cases import (
        SetCatchWeightConfigUseCase,
    )
    from backend.application.products.use_cases.product_meat_classification_use_cases import (
        ClassifyMeatProductUseCase,
        CreateAnatomicalRegionUseCase,
        CreateCutClassificationUseCase,
        CreateSpeciesUseCase,
        SetAnatomicalRegionActiveUseCase,
        SetCutClassificationActiveUseCase,
        SetSpeciesActiveUseCase,
    )
    from frontend.desktop.modules.products.meat_classification_presenter import (
        MeatClassificationPresenter,
    )
    return MeatClassificationPresenter(
        read_factory=lambda: (SpeciesCatalogQueryService(conn),
                              MeatClassificationQueryService(conn)),
        write_factory=lambda: {
            "create_species": CreateSpeciesUseCase(conn, authorization),
            "set_species_active": SetSpeciesActiveUseCase(conn, authorization),
            "create_region": CreateAnatomicalRegionUseCase(conn, authorization),
            "set_region_active": SetAnatomicalRegionActiveUseCase(conn, authorization),
            "create_cut": CreateCutClassificationUseCase(conn, authorization),
            "set_cut_active": SetCutClassificationActiveUseCase(conn, authorization),
            "classify_product": ClassifyMeatProductUseCase(conn, authorization),
            "catch_weight": SetCatchWeightConfigUseCase(conn, authorization),
        },
        product_read_factory=lambda: (ProductProfileQueryService(conn),
                                      UnitCatalogQueryService(conn)),
        has_permission=checker, session=session_context)


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
    from frontend.desktop.modules.products.pages.meat_classification_page import (
        MeatClassificationPage,
    )
    from frontend.desktop.modules.products.pages.audit_page import ProductAuditPage
    from frontend.desktop.modules.products.pages.notifications_page import (
        ProductNotificationsPage,
    )
    from frontend.desktop.modules.products.pages.settings_page import ProductSettingsPage
    from frontend.desktop.modules.products.pages.approvals_page import ApprovalsPage
    from frontend.desktop.modules.products.pages.data_quality_page import DataQualityPage
    from frontend.desktop.modules.products.pages.external_catalog_page import (
        ExternalCatalogPage,
    )
    from frontend.desktop.modules.products.products_view import ProductsView
    from frontend.desktop.components.icons import Icons
    from frontend.desktop.modules.products.navigation import PRODUCTS_NAV

    specs = (
        (ProductsOverviewPage, "Resumen"),
        (ProductCatalogPage, "Catálogo"),
        (ApprovalsPage, "Aprobaciones técnicas"),
        (DataQualityPage, "Calidad de datos"),
        (ProductCategoriesPage, "Categorías"),
        (ProductBrandsPage, "Marcas"),
        (ProductAttributesPage, "Atributos"),
        (MeatClassificationPage, "Clasificación cárnica"),
        (BranchChannelPage, "Sucursales y canales"),
        (ProductImportPage, "Importar"),
        (ExternalCatalogPage, "Catálogo externo"),
        (ProductNotificationsPage, "Notificaciones"),
        (ProductAuditPage, "Auditoría"),
        (ProductSettingsPage, "Configuración"),
    )
    navigation = {entry.page_id: entry for entry in PRODUCTS_NAV}
    section_icons = (
        navigation["products_overview"].icon,
        navigation["products_catalog"].icon,
        Icons.APPROVAL,
        Icons.QUALITY,
        navigation["products_categories"].icon,
        Icons.COMPANY,
        Icons.CHECKLIST,
        Icons.SPECIES,
        navigation["products_branches"].icon,
        navigation["products_imports"].icon,
        Icons.EXTERNAL,
        Icons.BELL,
        Icons.AUDIT,
        Icons.SETTINGS,
    )
    return ProductsView(presenter, specs, parent, section_icons=section_icons)


def create_products_view(connection, session_context=None, *, live_session=None, parent=None):
    """Factory used by `modulos/productos_enterprise.py`. Never receives
    the container itself — only what it needs, already unwrapped."""
    presenter = build_products_presenter(connection, session_context, live_session=live_session)
    return build_products_view(presenter, parent)
