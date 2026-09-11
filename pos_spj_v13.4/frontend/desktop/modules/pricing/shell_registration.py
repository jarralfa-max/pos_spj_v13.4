"""Registro de Precios y Costos en el shell canónico.

Como Activos, el módulo estaba construido —presentador, seis páginas,
navegación y modelos de vista— y no se podía abrir. A diferencia de Activos,
aquí SÍ hay datos detrás: `pricing_schema.py` crea las tablas, las migraciones
149 y 150 las siembran (la 150 rellena desde el modelo anterior) y
`PricingReadService` las consulta. Lo que faltaba era el widget que junta las
páginas —ahora `PricingWorkspace`— y este archivo.

UNA CONSECUENCIA QUE HAY QUE SABER ANTES DE BUSCAR LA ENTRADA EN EL MENÚ
-------------------------------------------------------------------------
Los permisos de este contexto son PLANOS (`PRICING_VIEW`), no `MODULO.accion`.
`permission_catalog.py` lo declara como deuda conocida y los deja fuera del
catálogo a propósito: inventarles un módulo sería fabricar vocabulario.

El efecto práctico: esta entrada del menú **sólo la verá el administrador**, que
lleva el comodín global. Para cualquier otro rol el código no es otorgable desde
Configuración → Seguridad → Permisos, porque esa matriz se construye desde el
catálogo. No es un fallo de este archivo — es el estado real del contexto, y es
el mismo que ya tiene `losses` (`LOSSES_VIEW`), que la guardia
`test_permission_catalog_matches_menu_modules` viene reportando.

Cerrarlo es convertir el vocabulario de Pricing a `PRECIOS.accion`, y eso NO se
hizo aquí a propósito: `tests/unit/pricing/test_pricing_authorization.py::
test_no_coarse_precios_permission` fija hoy lo contrario
(`all(c.startswith("PRICING_"))`). Los dos artefactos se contradicen y resolverlo
es una decisión, no una limpieza.
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
    from backend.application.pricing.queries.pricing_read_service import PricingReadService
    from frontend.desktop.modules.pricing.presenter import PricingPresenter
    from frontend.desktop.modules.pricing.pricing_workspace import PricingWorkspace

    presenter = PricingPresenter(
        read_service_factory=lambda: PricingReadService(connection),
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
