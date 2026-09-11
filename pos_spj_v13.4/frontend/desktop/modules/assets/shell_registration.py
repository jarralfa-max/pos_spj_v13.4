"""Registro de Activos en el shell canónico.

Hasta ahora el módulo estaba construido —12 archivos, presentador, espacio de
trabajo y páginas— y **no se podía abrir**: no tenía este archivo, que es lo que
el shell importa para saber que un módulo existe. Una pantalla completa sin
entrada de menú no falla nunca; simplemente no existe para el usuario.

ADVERTENCIA QUE HAY QUE LEER ANTES DE ESPERAR DATOS
----------------------------------------------------
Activos NO TIENE CAPA DE PERSISTENCIA. Comprobado: no hay ningún repositorio
SQLite (`backend/infrastructure/db/repositories/` no contiene nada de activos),
no hay tablas de activos en `backend/infrastructure/db/schema/`, y los puertos
de `backend/domain/assets/repository_ports.py` no tienen ni una implementación.

Por eso `query_services` va vacío abajo, y no por descuido: no hay ningún
servicio de consulta que se pueda construir. `AssetsPresenter` degrada cada
lectura a un resultado vacío en vez de reventar —está escrito así a
propósito— así que la pantalla ABRE y muestra estados vacíos, con la navegación
y los permisos funcionando.

Es decir: esta entrada de menú da acceso a un módulo que hoy no puede mostrar
ni registrar nada. Es visible y honesto (un estado vacío, no un error), pero
quien lo abra no va a encontrar datos hasta que exista la capa de persistencia.
Retirar la entrada es quitar su `NavigationItemDefinition` de
`migrated_modules_navigation.py`; el resto de este archivo no estorba.
"""
from __future__ import annotations

from typing import Optional

from backend.security.permissions.codes import module_view_permission
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

ASSETS_MODULE_ID = "assets"
ASSETS_ROUTE_ID = "assets.workspace"
ASSETS_VIEW_FACTORY_ID = "assets.workspace_view"

#: `ACTIVOS.ver`, que YA existe en `CANONICAL_MODULE_PERMISSIONS` — no un
#: permiso inventado para esta migración. Importa que sea punteado: un código
#: plano no tiene módulo, así que no se puede cotejar contra el catálogo ni
#: otorgar desde la matriz de Configuración, y la entrada quedaría invisible
#: para todos salvo el administrador, que lleva el comodín global y por eso no
#: lo notaría.
ASSETS_REQUIRED_PERMISSION = module_view_permission("ACTIVOS")


def build_assets_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=ASSETS_MODULE_ID,
        display_name="Activos",
        startup_mode=StartupMode.LAZY,
        routes=(ASSETS_ROUTE_ID,),
        permissions=frozenset({ASSETS_REQUIRED_PERMISSION}),
    )


def build_assets_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=ASSETS_ROUTE_ID,
        module_id=ASSETS_MODULE_ID,
        title="Activos",
        view_factory_id=ASSETS_VIEW_FACTORY_ID,
        breadcrumb=("Activos",),
        required_permission=ASSETS_REQUIRED_PERMISSION,
    )


def create_assets_view(connection, session_context):
    """Raíz de composición del módulo.

    `connection` se acepta y no se usa, y conviene que quede escrito: la firma
    es la que el shell invoca para todos los módulos, y el día que existan los
    repositorios de activos ésta es la línea donde se construyen los servicios
    de consulta. Dejarla fuera obligaría a cambiar también el activador.
    """
    from frontend.desktop.modules.assets.assets_presenter import AssetsPresenter
    from frontend.desktop.modules.assets.assets_workspace import AssetsWorkspace

    presenter = AssetsPresenter(
        session_context=session_context,
        # Vacío porque no hay nada que inyectar: ningún servicio de consulta de
        # activos se puede construir sin repositorios, y no existen.
        query_services={},
    )
    return AssetsWorkspace(presenter)


class AssetsModuleActivator:
    """`ModuleActivator` estructural, la misma convención que el resto.

    Registra la fábrica de vista real contra el registro vivo, con los dos
    únicos valores que `create_assets_view` necesita — nunca el paquete entero
    de dependencias de la aplicación, que es lo que las guardias de ASSET-1
    prohíben que llegue a la UI.
    """

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            ASSETS_VIEW_FACTORY_ID,
            lambda: create_assets_view(self._connection, self._session_context),
        )
