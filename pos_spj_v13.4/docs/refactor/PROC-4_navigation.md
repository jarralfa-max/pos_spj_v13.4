# PROC-4 — Sidebar y navegación: Procesamiento Cárnico

Estado: **DONE** (sidebar, rutas, permisos, badges, feature flags; sin páginas
funcionales ni cutover del menú global todavía)

## Alcance

Cascarón de navegación interno del módulo, siguiendo exactamente el patrón ya
validado en `frontend/desktop/modules/losses/` (la referencia más reciente):
un contrato de navegación declarativo puro (sin PyQt), un sidebar accesible
(`QListWidget`), un registro de rutas, páginas placeholder, y el contenedor
del workspace (`sidebar + QStackedWidget`, nunca `QTabWidget`).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `frontend/desktop/modules/meat_processing/navigation/meat_processing_sidebar.py` | `MeatProcessingNavEntry` (dataclass: `page_id`, `title`, `icon`, `permission`, `tooltip`, `badge_key`, `feature_flag`) + `MEAT_PROCESSING_NAV` (29 entradas: 19 estándar + 10 de sacrificio futuro) + `visible_entries(has_permission, badges, has_feature)`. Sin import de PyQt — es un contrato puro, verificado por test de arquitectura. |
| `frontend/desktop/modules/meat_processing/widgets/meat_processing_sidebar_widget.py` | `MeatProcessingSidebarWidget(QListWidget)` — accesible (`accessibleName`/`accessibleDescription`/`AccessibleTextRole` con conteo de badge), colapsable en breakpoint compacto, emite `route_requested`. |
| `frontend/desktop/modules/meat_processing/pages/placeholder_page.py` | `MeatProcessingPlaceholderPage` — usa `PageHeader` + `ViewState.EMPTY` del Design System; cero SQL, cero lógica de negocio. |
| `frontend/desktop/modules/meat_processing/meat_processing_routes.py` | `MEAT_PROCESSING_ROUTES` (dict `page_id → NavEntry`) + `build_page()`. |
| `frontend/desktop/modules/meat_processing/meat_processing_view.py` | `MeatProcessingView` — sidebar + `QStackedWidget`, layout responsivo (`apply_responsive_layout` colapsa bajo `ResponsiveBreakpoints.COMPACT`). |

## Permisos (extensión de PROC-1)

El prompt maestro §50 no listaba un permiso `VIEW` por cada pestaña del
sidebar (solo permisos de acción granulares). Siguiendo el precedente de
Losses (`LossPermissions.OVERVIEW_VIEW`, `.REGISTRATION_VIEW`, …, un `VIEW`
por pestaña), se añadieron 11 permisos nuevos a `MeatProcessingPermissions`
(PROC-1) para las pestañas que no tenían un permiso de solo-lectura dedicado:
`PREPARATION_VIEW`, `ACTIVE_PROCESSING_VIEW`, `CUTTING_VIEW`,
`DERIVED_PRODUCTS_VIEW`, `PACKAGING_LABELING_VIEW`, `PRODUCED_LOTS_VIEW`,
`QUALITY_VIEW`, `INCIDENTS_VIEW`, `TRACEABILITY_VIEW`, `ALERTS_VIEW`,
`ANALYTICS_VIEW`. Sus sufijos de acción se registraron en
`core/security/permission_catalog.py["PRODUCCION"]` (mismo patrón Compras
que PROC-1 estableció) — verificado automáticamente por
`test_every_permission_action_suffix_is_registered_in_the_canonical_catalog`
(PROC-1), que sigue en verde tras la extensión.

Las 10 pestañas de "Sacrificio futuro" reutilizan los permisos de acción
`SLAUGHTER_*` ya definidos en PROC-1 (`SLAUGHTER_ANIMAL_RECEPTION`,
`SLAUGHTER_EXECUTE`, etc.) en vez de duplicar un set `SLAUGHTER_*_VIEW`
paralelo — son secciones aún no funcionales tras un feature flag; si
Sacrificio necesita permisos de vista distintos de los de acción cuando se
construya de verdad (PROC-24), se separan en ese momento.

## Feature flags (§37/§58)

`MeatProcessingNavEntry.feature_flag: str | None`. Las 10 secciones de
Sacrificio futuro comparten la constante `SLAUGHTER_FEATURE_FLAG =
"slaughter_features_enabled"` (nombre tomado literalmente del prompt maestro
§58). `visible_entries()` las oculta salvo que **tanto** el permiso **como**
el flag estén concedidos — el default de `has_feature` cuando no se provee es
"todo apagado" (fail-safe: una sección futura nunca aparece por accidente).

No se conectó a `ModuleSettingsQueryService.get_branch_feature_flags()` (el
mecanismo real de feature flags del sistema, `repositories/feature_flag_repository.py`)
todavía — ese repositorio sigue tipando `branch_id` como `int` (deuda legacy
propia, fuera del alcance de este bounded context) y no hay todavía un Use
Case real que necesite consumirlo. `visible_entries()` acepta cualquier
`Callable[[str], bool]`, así que conectarlo es un cambio de una línea cuando
exista el punto de integración real (PROC-6+ o el cutover de PROC-23).

## Badges

6 de las 19 pestañas estándar declaran `badge_key` (proporción similar a
Losses): `orders_needing_attention` (Órdenes), `active_orders` (En proceso),
`yield_out_of_tolerance` (Rendimientos), `pending_quality` (Calidad),
`open_incidents` (Incidencias), `critical_alerts` (Alertas). Los valores de
badge son responsabilidad externa (un futuro `QueryService`) — `visible_entries`
solo los adjunta si están presentes en el mapping recibido.

## Decisión de alcance: sin cutover del menú global

`interfaz/menu_lateral.py` conserva el único botón existente
(`"🔪 Procesamiento Cárnico"` → `"PRODUCCION"`) apuntando a
`modulos/produccion.py`. `interfaz/main_window.py` no importa nada de
`frontend/desktop/modules/meat_processing/`. Verificado por
`test_legacy_produccion_menu_entry_and_module_are_not_touched_yet`. El nuevo
módulo es standalone e importable/testeable de forma aislada — el patrón que
ya siguió PROC-3 con el esquema. El cutover real (reemplazar el botón legacy
por el nuevo host, como ya hizo Losses con `LossesModuleHost`) es trabajo de
PROC-23, y solo después de que las páginas placeholder tengan contenido
funcional real.

## Tests

`tests/unit/meat_processing/test_meat_processing_navigation.py` (contrato de
navegación puro: 29 entradas, permisos únicos con prefijo `PRODUCCION.`,
filtrado por permiso, ocultamiento de Sacrificio sin flag, aparición con
flag+permiso, badges externos, "solo lectura" no infiere secciones sensibles),
`test_meat_processing_routes.py` (toda entrada tiene ruta, ruta desconocida
lanza `KeyError`), `test_meat_processing_ui_ux_unittest.py` (offscreen-safe,
mirror de `test_losses_ui_ux_unittest.py`: accesibilidad, badges,
colapso responsivo, ruta inicial, placeholder), y
`tests/architecture/test_meat_processing_sidebar_navigation.py` (sidebar+stack
no tabs, sin SQL/repositorios en páginas, sin iconografía de emoji, menú
legacy intacto, contrato de navegación sin import de PyQt).

## Pendiente

- Páginas funcionales reales (overview con KPIs, órdenes con tabla, etc.) —
  fases PROC-5 en adelante, cada una reemplaza su placeholder correspondiente.
- Conectar `has_feature`/badges a fuentes reales (`ModuleSettingsQueryService`,
  un futuro `MeatProcessingDashboardQueryService`) cuando existan los Use
  Cases que las alimenten.
- Cutover del menú global (`interfaz/menu_lateral.py`/`main_window.py`) —
  PROC-23/PROC-25, no antes de tener páginas funcionales con paridad completa
  respecto a `modulos/produccion.py`.
