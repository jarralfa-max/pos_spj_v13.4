"""Desktop composition root for the Procesamiento Cárnico workspace (PROC-23).

First functional page: Órdenes (mp_processing_orders). Every other
MEAT_PROCESSING_NAV entry still falls back to the PROC-4 placeholder — full
page-by-page buildout is incremental, matching every prior PROC phase's own
scoping discipline. The sidebar's legacy "PRODUCCION" button
(interfaz/menu_lateral.py) still launches modulos/produccion.py; this host
is not wired into main_window.py yet — cutover only happens once page
parity is real (§4/PROC-4's own stated deferral), to avoid removing access
to still-legacy-only functionality (CLAUDE.md Regla 0).
"""

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.queries import ProcessingOrderQueryService
from backend.application.meat_processing.session_authorization import (
    MeatProcessingSessionPermissionChecker,
)
from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CloseProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    ReleaseProcessingOrderUseCase,
)
from backend.application.queries.product_query_service import ProductQueryService
from frontend.desktop.modules.meat_processing.meat_processing_routes import build_page
from frontend.desktop.modules.meat_processing.meat_processing_view import MeatProcessingView
from frontend.desktop.modules.meat_processing.pages import ProcessingOrdersPage
from frontend.desktop.modules.meat_processing.presenters import ProcessingOrderPresenter


class MeatProcessingModuleHost(MeatProcessingView):
    def __init__(self, container, parent=None) -> None:
        session = getattr(container, "session", None)
        has_permission = (
            session.tiene_permiso
            if session is not None and hasattr(session, "tiene_permiso")
            else lambda _permission: False
        )
        authorization = MeatProcessingAuthorizationPolicy(
            MeatProcessingSessionPermissionChecker(session))

        def context_provider() -> MeatProcessingExecutionContext:
            actor = str(getattr(session, "user_id", "") or "")
            branch = str(getattr(session, "active_branch_id", "") or "")
            # `SessionContext`/`LegacySessionAdapter` exponen
            # `active_warehouse_id`; ninguno define `warehouse_id`, así que
            # leer sólo ese alias dejaba `allowed_warehouse_ids={""}` (§17).
            # Mismo orden que ya resuelve el `ProcessingOrderPresenter` de
            # este mismo módulo.
            warehouse = str(getattr(session, "active_warehouse_id", None)
                            or getattr(session, "warehouse_id", None) or "")
            permissions = frozenset(
                code for code in getattr(session, "permisos", ())
                if isinstance(code, str))
            return MeatProcessingExecutionContext(
                actor_user_id=actor, active_branch_id=branch,
                assigned_branch_ids=frozenset({branch}),
                allowed_warehouse_ids=frozenset({warehouse}),
                permissions=permissions,
            )

        orders_presenter = ProcessingOrderPresenter(
            connection_provider=lambda: container.db,
            query_factory=ProcessingOrderQueryService,
            product_query_factory=ProductQueryService.from_connection,
            create_uc=CreateProcessingOrderUseCase(authorization),
            approve_uc=ApproveProcessingOrderUseCase(authorization),
            release_uc=ReleaseProcessingOrderUseCase(authorization),
            close_uc=CloseProcessingOrderUseCase(authorization),
            session_context=session,
            context_provider=context_provider,
        )

        def page_builder(page_id: str):
            if page_id == "mp_processing_orders":
                return ProcessingOrdersPage(orders_presenter)
            return build_page(page_id)

        super().__init__(
            has_permission=has_permission,
            badges={},
            has_feature=lambda _flag: False,  # sacrificio: PROC-24 stub, no habilitado
            page_builder=page_builder,
            parent=parent,
        )
