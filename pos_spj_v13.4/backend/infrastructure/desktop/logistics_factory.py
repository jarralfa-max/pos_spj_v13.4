"""Raíz de composición del módulo Logística (integración Logística 32cfbf).

Una sola composición de los servicios de Logística (`build_logistics_services`).
«Compra en origen» reutiliza la composición de Compras y su página
(`LogisticsRelatedPage`): es la misma pantalla con otra entrada, no una copia.
Si Compras no está instalado, la ruta lo dice en vez de quedar vacía.
"""

from __future__ import annotations


def _installed(capability_id: str) -> bool:
    try:
        from backend.application.software_updates.installation import (
            enabled_capabilities_for,
        )
        from backend.shared.app_paths import AppPaths
        return enabled_capabilities_for(AppPaths.from_environment()).is_enabled(capability_id)
    except Exception:  # noqa: BLE001 - sin configuración de instalación, todo instalado
        return True


def create_logistics_view(connection, session_context=None, *, parent=None,
                          secret_store=None):
    from backend.application.logistics.composition import build_logistics_services
    from backend.application.logistics.container_catalog import ContainerCatalogService
    from backend.application.logistics.queries import LogisticsContainerQueryService
    from frontend.desktop.modules.logistics.logistics_presenter import LogisticsPresenter
    from frontend.desktop.modules.logistics.logistics_view import LogisticsView
    from frontend.desktop.modules.logistics.pages import (
        ContainersPage,
        ShipmentsPage,
        UnavailablePage,
    )

    has_permission = (session_context.tiene_permiso
                      if session_context is not None and hasattr(session_context, "tiene_permiso")
                      else (lambda _code: False))
    service, queries = build_logistics_services(connection, session_context,
                                                secret_store=secret_store)
    from backend.application.logistics.container_labels import ContainerLabelService
    from backend.infrastructure.printing.container_label_renderer import (
        ReportlabContainerLabelRenderer,
    )
    container_queries = LogisticsContainerQueryService(connection)
    presenter = LogisticsPresenter(
        queries=container_queries,
        catalog=ContainerCatalogService(service, connection), session_context=session_context,
        labels=ContainerLabelService(service, container_queries,
                                     ReportlabContainerLabelRenderer()))

    def origin_page():
        if not _installed("purchasing"):
            return UnavailablePage(
                "Compra en origen",
                "Requiere el módulo Compras. Agrégalo desde el instalador (Reparar → "
                "Personalizado → Compras y proveedores).")
        from frontend.desktop.modules.purchasing.enterprise_routes import (
            build_enterprise_presenter,
        )
        from frontend.desktop.modules.purchasing.pages.logistics_related_page import (
            LogisticsRelatedPage,
        )
        from frontend.desktop.modules.purchasing.direct_purchase_routes import (
            build_direct_purchase_presenter,
        )
        from frontend.desktop.modules.purchasing.direct_purchase_view import (
            DirectPurchaseCreateView,
        )
        compras = build_enterprise_presenter(connection, session_context,
                                             logistics_service=service,
                                             logistics_queries=queries)
        directa = build_direct_purchase_presenter(connection, session_context)
        return LogisticsRelatedPage(
            compras, capabilities=compras.capabilities(),
            direct_purchase_factory=lambda: DirectPurchaseCreateView(directa))

    def page_builder(page_id: str):
        if page_id == "lg_containers":
            return ContainersPage(presenter)
        if page_id == "lg_shipments":
            return ShipmentsPage(presenter)
        if page_id == "lg_origin":
            return origin_page()
        raise KeyError(f"Ruta de Logística desconocida: {page_id}")

    return LogisticsView(has_permission=has_permission, page_builder=page_builder,
                         parent=parent)
