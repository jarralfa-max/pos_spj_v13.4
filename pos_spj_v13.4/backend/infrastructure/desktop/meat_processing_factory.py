"""Desktop composition root for the Procesamiento Cárnico workspace (PROC-23).

Una sola composición sirve a los DOS anfitriones: `create_meat_processing_view`
(shell canónico, vía `MeatProcessingModuleActivator`) y
`MeatProcessingModuleHost` (adaptador del `AppContainer` legacy). §3 prohíbe
que cada uno arme el suyo.

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
from backend.domain.meat_processing.slaughter.feature_flag import SLAUGHTER_ENABLED
from frontend.desktop.modules.meat_processing.meat_processing_routes import build_page
from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (
    SLAUGHTER_FEATURE_FLAG,
)
from frontend.desktop.modules.meat_processing.meat_processing_view import MeatProcessingView
from frontend.desktop.modules.meat_processing.pages import ProcessingOrdersPage
from frontend.desktop.modules.meat_processing.presenters import ProcessingOrderPresenter


def _build_meat_processing_wiring(connection, session_context=None):
    """ÚNICA composición del workspace de Procesamiento Cárnico.

    Misma forma que `_build_transfers_presenter_and_permission`: recibe sólo
    lo que necesita —conexión y sesión ya desempaquetadas—, nunca el
    `AppContainer`. La consumen los dos anfitriones del módulo
    (`create_meat_processing_view` para el shell nuevo y
    `MeatProcessingModuleHost` para el slot legacy), de modo que ninguno
    pueda componer una versión propia y divergente (§3).
    """
    has_permission = (
        session_context.tiene_permiso
        if session_context is not None and hasattr(session_context, "tiene_permiso")
        else lambda _permission: False
    )
    authorization = MeatProcessingAuthorizationPolicy(
        MeatProcessingSessionPermissionChecker(session_context))

    def context_provider() -> MeatProcessingExecutionContext:
        actor = str(getattr(session_context, "user_id", "") or "")
        branch = str(getattr(session_context, "active_branch_id", "") or "")
        # `SessionContext`/`LegacySessionAdapter` exponen
        # `active_warehouse_id`; ninguno define `warehouse_id`, así que
        # leer sólo ese alias dejaba `allowed_warehouse_ids={""}` (§17).
        # Mismo orden que ya resuelve el `ProcessingOrderPresenter` de
        # este mismo módulo.
        warehouse = str(getattr(session_context, "active_warehouse_id", None)
                        or getattr(session_context, "warehouse_id", None) or "")
        permissions = frozenset(
            code for code in getattr(session_context, "permisos", ())
            if isinstance(code, str))
        return MeatProcessingExecutionContext(
            actor_user_id=actor, active_branch_id=branch,
            assigned_branch_ids=frozenset({branch}),
            allowed_warehouse_ids=frozenset({warehouse}),
            permissions=permissions,
        )

    orders_presenter = ProcessingOrderPresenter(
        connection_provider=lambda: connection,
        query_factory=ProcessingOrderQueryService,
        product_query_factory=ProductQueryService.from_connection,
        create_uc=CreateProcessingOrderUseCase(authorization),
        approve_uc=ApproveProcessingOrderUseCase(authorization),
        release_uc=ReleaseProcessingOrderUseCase(authorization),
        close_uc=CloseProcessingOrderUseCase(authorization),
        session_context=session_context,
        context_provider=context_provider,
    )

    def page_builder(page_id: str):
        if page_id == "mp_processing_orders":
            return ProcessingOrdersPage(orders_presenter)
        return build_page(page_id)

    return has_permission, page_builder


def _has_slaughter_feature(flag: str) -> bool:
    """Las 10 entradas de sacrificio del sidebar se gobiernan con la MISMA
    constante que el dominio (`SLAUGHTER_ENABLED`), no con un `False`
    escrito a mano aquí: dos fuentes de verdad para "¿está habilitado el
    sacrificio?" se desincronizan en cuanto alguien encienda una (§3).
    """
    return SLAUGHTER_ENABLED and flag == SLAUGHTER_FEATURE_FLAG


def create_meat_processing_view(
    connection, session_context=None, *, parent=None,
) -> MeatProcessingView:
    """Equivalente de `MeatProcessingModuleHost` con dependencias explícitas —
    lo llama `MeatProcessingModuleActivator` del shell canónico.

    Antes ese activator armaba su propio
    `MeatProcessingView(page_builder=build_page)`: las 29 rutas en
    placeholder —incluida `mp_processing_orders`, que sí tiene página real—,
    sin presenter ni casos de uso, y con un `_has_permission` que sondeaba
    `has_permission`/`permissions`, atributos que ni `SessionContext` ni
    `LegacySessionAdapter` definen, así que el sidebar salía vacío.
    """
    has_permission, page_builder = _build_meat_processing_wiring(
        connection, session_context)
    return MeatProcessingView(
        has_permission=has_permission, badges={},
        has_feature=_has_slaughter_feature, page_builder=page_builder,
        parent=parent,
    )


class MeatProcessingModuleHost(MeatProcessingView):
    """Adaptador del `AppContainer` legacy: desempaqueta el contenedor y
    delega en la composición común. No compone nada por su cuenta (§4)."""

    def __init__(self, container, parent=None) -> None:
        has_permission, page_builder = _build_meat_processing_wiring(
            container.db, getattr(container, "session", None))
        super().__init__(
            has_permission=has_permission,
            badges={},
            has_feature=_has_slaughter_feature,
            page_builder=page_builder,
            parent=parent,
        )
