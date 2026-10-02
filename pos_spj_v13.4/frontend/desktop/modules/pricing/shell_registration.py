"""Registro de Precios y Costos en el shell canónico.

Como Activos, el módulo estaba construido —presentador, seis páginas,
navegación y modelos de vista— y no se podía abrir. A diferencia de Activos,
aquí SÍ hay datos detrás: `pricing_schema.py` crea las tablas, las migraciones
149 y 150 las siembran (la 150 rellena desde el modelo anterior) y
`PricingReadService` las consulta. Lo que faltaba era el widget que junta las
páginas —ahora `PricingWorkspace`— y este archivo.

PERMISOS — CERRADO EL 2026-09-16 (esta nota documentaba lo contrario)
---------------------------------------------------------------------
Los permisos de este contexto ERAN planos (`PRICING_VIEW`) y quedaban fuera del
catálogo, así que la entrada del menú sólo la veía el administrador (por comodín
global) y ningún otro rol podía recibirlos desde Configuración → Seguridad →
Permisos.

Ya no: el vocabulario migró a `PRECIOS.<accion>`, `pricing` salió de
`FLAT_CODE_CONTEXTS` y el catálogo lo publica solo. Sus acciones son otorgables
como las de cualquier otro módulo. La migración no dejó nada inerte porque
`PRECIOS` nunca estuvo sembrado en `rol_permisos` — no había concesiones gruesas
que retirar, a diferencia de lo que hizo la migración 179 con Inventario.

Una corrección a lo que decía esta nota: `test_no_coarse_precios_permission`
fijaba `all(c.startswith("PRICING_"))` y era el artefacto que sostenía la deuda;
se reemplazó al tomar la decisión.

La guardia `tests/architecture/test_permission_catalog_matches_menu_modules.py`
que citaba esta nota SÍ existe (sus funciones tienen otro nombre que el archivo,
que es lo que despista al buscarla) y era correcta: reportaba Precios junto con
Mermas. Tras la migración ya sólo reporta `LOSSES_VIEW`.
"""
from __future__ import annotations

from typing import Optional

from backend.application.pricing.permissions import PricingPermissions
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

PRICING_MODULE_ID = "pricing"
PRICING_ROUTE_ID = "pricing.workspace"
PRICING_VIEW_FACTORY_ID = "pricing.workspace_view"

#: El código real del contexto, no uno traducido a mano para que la guardia del
#: catálogo pase. Traducirlo aquí daría dos vocabularios para lo mismo y haría
#: que el menú dejara pasar a quien el módulo luego deniega.
PRICING_REQUIRED_PERMISSION = PricingPermissions.VIEW


def build_pricing_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=PRICING_MODULE_ID,
        display_name="Precios y Costos",
        startup_mode=StartupMode.LAZY,
        routes=(PRICING_ROUTE_ID,),
        permissions=frozenset({PRICING_REQUIRED_PERMISSION}),
    )


def build_pricing_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=PRICING_ROUTE_ID,
        module_id=PRICING_MODULE_ID,
        title="Precios y Costos",
        view_factory_id=PRICING_VIEW_FACTORY_ID,
        breadcrumb=("Precios y Costos",),
        required_permission=PRICING_REQUIRED_PERMISSION,
    )


def _session_permission_checker(session_context):
    """Cierra en denegar cuando no hay sesión.

    Sin esto, una vista construida fuera de una sesión real enseñaría las seis
    secciones: el fallo no se vería porque la pantalla funcionaría.
    """
    comprobar = getattr(session_context, "tiene_permiso", None)
    if not callable(comprobar):
        return lambda _code: False
    return lambda code: bool(comprobar(code))


def create_pricing_view(connection, session_context):
    """Raíz de composición del módulo.

    El servicio de lectura se construye PEREZOSAMENTE, una vez por consulta, y
    no se guarda: `PricingReadService` sólo envuelve la conexión, y retenerlo
    ataría la vista a la conexión que había cuando se abrió.
    """
    from backend.application.pricing.authorization.policy import (
        PricingAuthorizationPolicy,
    )
    from backend.application.pricing.queries.pricing_read_service import PricingReadService
    from backend.application.pricing.session_authorization import (
        PricingSessionPermissionChecker,
    )
    from backend.application.pricing.use_cases import (
        ActivatePriceListUseCase,
        ApplyPriceToSelectionUseCase,
        ApprovePriceListUseCase,
        CreatePriceListUseCase,
        DeactivatePriceListUseCase,
        DuplicatePriceListUseCase,
        SetProductPriceUseCase,
        SetVolumePriceUseCase,
        SubmitPriceListUseCase,
    )
    from backend.application.products.queries.product_category_query_service import (
        ProductCategoryQueryService,
    )
    from backend.application.products.queries.product_selection_query_service import (
        ProductCatalogSearchQueryService,
    )
    from backend.application.pricing.use_cases.cost_policy_use_cases import (
        SetCostPolicyUseCase,
    )
    from frontend.desktop.modules.pricing.presenter import PricingPresenter
    from frontend.desktop.modules.pricing.pricing_workspace import PricingWorkspace

    # RBAC real: la política sin checker PERMITE todo, y este módulo mueve
    # dinero. Ver `PricingSessionPermissionChecker` para por qué aquí NO hay
    # traducción de códigos y qué implica (sólo el administrador opera).
    authorization = PricingAuthorizationPolicy(
        PricingSessionPermissionChecker(session_context))

    # Autorización EN CALIENTE (vender bajo el mínimo): la valida otra persona
    # sobre el terminal de quien vende, así que no puede resolverse contra la
    # sesión. Este verificador consulta `rol_permisos` para cualquier usuario,
    # acotado a la sucursal activa.
    from backend.application.security.authorizer_permission_checker import (
        AuthorizerPermissionChecker,
    )
    authorizer_authorization = PricingAuthorizationPolicy(
        AuthorizerPermissionChecker(
            connection,
            branch_id=str(getattr(session_context, "active_branch_id", "") or "") or None))

    presenter = PricingPresenter(
        read_service_factory=lambda: PricingReadService(connection),
        connection_provider=lambda: connection,
        use_cases={
            "create_list": CreatePriceListUseCase(authorization),
            "submit_list": SubmitPriceListUseCase(authorization),
            "approve_list": ApprovePriceListUseCase(authorization),
            "activate_list": ActivatePriceListUseCase(authorization),
            "deactivate_list": DeactivatePriceListUseCase(authorization),
            "duplicate_list": DuplicatePriceListUseCase(authorization),
            "set_price": SetProductPriceUseCase(authorization, authorizer_authorization),
            "set_volume": SetVolumePriceUseCase(authorization),
            # La selección por categoría se resuelve con el contrato compartido
            # de Productos, no con una consulta propia de Precios.
            "apply_bulk": ApplyPriceToSelectionUseCase(
                authorization,
                lambda: ProductCatalogSearchQueryService(connection)),
            "set_cost_policy": SetCostPolicyUseCase(authorization),
        },
        product_search_factory=lambda: ProductCatalogSearchQueryService(connection),
        category_query_factory=lambda: ProductCategoryQueryService(connection),
        session_context=session_context,
    )
    return PricingWorkspace(
        presenter, has_permission=_session_permission_checker(session_context))


class PricingModuleActivator:
    """`ModuleActivator` estructural, misma convención que el resto."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            PRICING_VIEW_FACTORY_ID,
            lambda: create_pricing_view(self._connection, self._session_context),
        )
