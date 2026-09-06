"""Business Intelligence registration into the new shell.

Módulo 11 de la migración módulo a módulo fuera del contenedor legacy
(1-10: `sales_pos`, `customers_crm`, `finance`, `hr`, `inventory`,
`products`, `purchasing`, `transfers`, `cash_register`, `configuracion`).
Sigue el mismo patrón que `transfers/shell_registration.py`.

Por qué este módulo sí y otros del mismo lote no: `business_intelligence`
construye páginas **reales** en 10 de sus 13 rutas
(`_REAL_ROUTE_BUILDERS` en `business_intelligence_routes.py`: ejecutivo,
ventas, inventario, compras, finanzas, forecast, recomendaciones,
escenarios, alertas, reportes). Sus 3 rutas restantes caen a un
placeholder explícito. `orders_delivery` sólo tiene 3 de 23 reales —
cablear un módulo así sería registrar pantallas vacías, no migrar
funcionalidad (§2).

CORRECCIÓN: este docstring afirmaba que `losses` y `meat_processing`
devuelven placeholder en **todas** sus rutas. Es falso, y el error venía de
medir sobre `<módulo>_routes.build_page()` en vez del `page_builder` que
pasa el composition root: `losses` tiene 4 rutas reales y
`meat_processing` 1 (ver 87c00096 y 02d348bf). Siguen sin ser candidatos a
corte —12 de 16 y 28 de 29 rutas sí son placeholder—, pero la razón es esa,
no "todas".

`BusinessIntelligenceView` ya acepta `connection`/`branch_id`/
`actor_user_id` y arma su propio `page_builder` con ellos, así que este
activator no reimplementa esa composición: le entrega los tres valores que
la vista ya sabe usar.

No se cablea en `main.py`/`MainWindow`/`MenuLateral` en esta ronda,
igual que los diez módulos anteriores: el slot `INTELIGENCIA_BI` del menú
legacy sigue siendo la ruta viva hasta que `main.py` corte al shell nuevo.
"""
from __future__ import annotations

from typing import Optional

from core.security.permission_catalog import permission_code
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.session_access import (
    active_branch_id,
    actor_user_id,
    sidebar_permission_checker,
)
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

BUSINESS_INTELLIGENCE_MODULE_ID = "business_intelligence"
BUSINESS_INTELLIGENCE_ROUTE_ID = "business_intelligence.workspace"
BUSINESS_INTELLIGENCE_VIEW_FACTORY_ID = "business_intelligence.workspace_view"

# Código real del catálogo (`core/security/permission_catalog.py`), no un
# permiso inventado para esta migración.
BUSINESS_INTELLIGENCE_REQUIRED_PERMISSION = permission_code("INTELIGENCIA_BI", "ver")


def build_business_intelligence_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=BUSINESS_INTELLIGENCE_MODULE_ID,
        display_name="Inteligencia de Negocios",
        startup_mode=StartupMode.LAZY,
        routes=(BUSINESS_INTELLIGENCE_ROUTE_ID,),
        permissions=frozenset({BUSINESS_INTELLIGENCE_REQUIRED_PERMISSION}),
    )


def build_business_intelligence_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=BUSINESS_INTELLIGENCE_ROUTE_ID,
        module_id=BUSINESS_INTELLIGENCE_MODULE_ID,
        title="Inteligencia de Negocios",
        view_factory_id=BUSINESS_INTELLIGENCE_VIEW_FACTORY_ID,
        breadcrumb=("Inteligencia de Negocios",),
        required_permission=BUSINESS_INTELLIGENCE_REQUIRED_PERMISSION,
    )


class BusinessIntelligenceModuleActivator:
    """Un `ModuleActivator` (SHELL-13) — estructural, no heredado, misma
    convención que los diez activators ya migrados. Recibe exactamente la
    firma que `_standard_activator_factory` entrega, sin contenedor global."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def _build_view(self):
        """La vista arma su propio `page_builder` a partir de
        `connection`/`branch_id`/`actor_user_id` (BI-23), así que aquí NO se
        recompone nada: sólo se lee la sesión.

        El `SidebarResolver` ya filtró la entrada al módulo con
        `required_permission`; el callback de abajo gobierna el sidebar
        INTERNO. Estaba roto: el `_has_permission` local sondeaba
        `has_permission`/`permissions`, atributos que ni `SessionContext` ni
        `LegacySessionAdapter` definen —ambos hablan `tiene_permiso`/
        `permisos`—, así que devolvía False siempre y las 10 rutas reales de
        este módulo quedaban INALCANZABLES tras un sidebar vacío. Ahora usa
        la derivación compartida del shell (§26).
        """
        from frontend.desktop.modules.business_intelligence.business_intelligence_view import (
            BusinessIntelligenceView,
        )

        session = self._session_context
        return BusinessIntelligenceView(
            has_permission=sidebar_permission_checker(session),
            connection=self._connection,
            branch_id=active_branch_id(session),
            actor_user_id=actor_user_id(session),
        )

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(BUSINESS_INTELLIGENCE_VIEW_FACTORY_ID, self._build_view)
