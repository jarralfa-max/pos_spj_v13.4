# CRM-14 — UI Foundations: rutas, sidebar, PageHeader, density, theme, IconProvider

Fecha: 2026-08-13. Primer código en `frontend/desktop/modules/customers_crm/`
(CRM-1 solo había dejado el paquete vacío). Fuente de diseño:
`docs/refactor/customers_crm_master_prompt.md` §7-10, §79-90; guardrails
`tests/architecture/test_customers_crm_routes_are_stable.py` y las otras
seis pruebas de UI de CRM-1 (`uses_canonical_design_system`,
`has_no_emoji_icons`, `has_no_hardcoded_colors`, `has_no_inline_styles`,
`ui_does_not_receive_app_container`, `ui_has_no_repositories`,
`ui_has_no_sql`).

## Hallazgo previo a escribir código: `ModuleSidebar` e `IconProvider` no existen con ese nombre

El master prompt nombra `ModuleSidebar` (§8) e `IconProvider` (§79) como si
fueran clases concretas. Investigación directa del árbol real de
`frontend/desktop/components/` + `frontend/desktop/themes/` encontró que
**ninguna de las dos existe literalmente** — son nombres aspiracionales del
prompt. Los mecanismos reales, ya usados por los módulos recién
refactorizados (`cash_register`, `transfers`), son:

- **`SideNav`** (`frontend/desktop/components/side_nav.py`) — la navegación
  lateral interna real que todo módulo ya construido usa.
- **`Icons`** + `icon_accessible_name()` (`frontend/desktop/components/
  icons.py`) — catálogo de identificadores semánticos de icono (strings
  ASCII, sin glifo real todavía — "transicional... swappable por SVG/icon-
  font más adelante" según su propio docstring).

Esta fase usa `SideNav`/`Icons`, no los nombres del prompt — mismo criterio
que CRM-2 ya aplicó al formato de permisos (adoptar la convención real del
repo sobre el nombre literal del prompt cuando entran en conflicto).

## Decisión de alcance: "sidebar" es la navegación INTERNA del módulo, no el registro en el menú global de la app

`interfaz/menu_lateral.py` (registro global de módulos, botón + código de
módulo) e `interfaz/main_window.py` (mapea código de módulo → clase host)
son archivos legacy, compartidos por TODA la aplicación, que ningún módulo
CRM anterior había tocado — y que ninguno de los 22 guardrails de CRM-1
escanea. Investigación encontró además un choque de nombres real: ya existe
un botón `"👥 Clientes"` con código `"CLIENTES"` apuntando al módulo legacy;
el namespace de permisos de este bounded context (`CustomerPermissions.*`,
CRM-2) también usa el prefijo `"CLIENTES."`, así que registrar una segunda
entrada ahí requeriría o bien reutilizar el mismo código de módulo (con
riesgo real de que `main_window.py::_conectar` sobrescriba el host legacy)
o bien inventar un código nuevo sin permiso equivalente en el catálogo.

Dado que (1) el subtema "sidebar" que el usuario invocó corresponde
literalmente a §8, titulado **"Navegación interna enterprise"** — no
registro global — y (2) el módulo hoy no tiene ninguna página real que
valga la pena exponer a un usuario final todavía (ver más abajo), esta fase
construye únicamente la navegación interna (`SideNav` + rutas propias del
módulo). El registro en el menú global de la app queda diferido a cuando
el módulo tenga contenido real que mostrar, y su propia decisión de diseño
(código de módulo nuevo vs. reemplazar `"CLIENTES"`) se documenta aquí como
pendiente, no resuelta a la ligera en una fase de "foundations".

## Qué se construyó

`frontend/desktop/modules/customers_crm/`:

- **`view_models.py`** — `CustomerCrmCapabilities`: un flag booleano por
  GRUPO de navegación (12: `module_view` + 11 grupos de §8), no uno por
  cada una de las 61 rutas — deliberadamente más grueso que
  `cash_register`'s `CashCapabilities` (que tiene un flag por acción
  granular), porque CRM-14 es *foundations*, no las páginas reales. Cuando
  una fase futura construya páginas de verdad para un grupo, esa página
  puede introducir su propio flag más fino sin tener que rediseñar este
  dataclass.
- **`capability_resolver.py`** — `resolve_customer_crm_capabilities(can)`:
  mapea cada grupo a un permiso ya existente (`CustomerPermissions.VIEW`,
  `CRMPermissions.LEADS_VIEW`, etc., construidos entre CRM-2 y CRM-13) —
  **cero permisos nuevos necesarios** para esta fase, primera vez en el
  pipeline que una fase entera no toca `permission_catalog.py`.
- **`customers_crm_routes.py`** — `CustomerCrmRoute` (campo `route_id`, no
  `key` como `cash_register`, porque el guardrail de CRM-1 exige
  literalmente ese nombre de campo), **las 61 rutas canónicas de §9
  completas**, agrupadas según §8, `visible_routes()`/`grouped_routes()`
  (mismo patrón que `cash_register_routes.py`). Donde el texto condensado
  del prompt no da una correspondencia 1:1 explícita entre las etiquetas de
  §8 y las rutas de §9 dentro de un grupo, el emparejamiento es
  interpretación semántica de esta fase (p.ej. "Notas" de Actividades se
  asignó a `crm.activities`, ya que §9 no tiene una ruta `crm.notes`
  dedicada) — documentado aquí, no adivinado en silencio.
- **`customers_crm_presenter.py`** — `CustomerCrmPresenter`: puente delgado
  (`.can()`, `.capabilities()`, `.query_service()`, `.use_case()`), mismo
  patrón que `CashRegisterPresenter`. `query_services`/`use_cases` son
  diccionarios vacíos por defecto a propósito — conectar cada uno de los
  ~50 QueryServices/UseCases ya construidos entre CRM-3 y CRM-13 a una
  página es trabajo de la fase que construya esa página, no de esta.
- **`customers_crm_workspace.py`** — `CustomersCrmWorkspace`: `PageHeader`
  (`icon=Icons.CUSTOMERS`) + `SideNav` + `QStackedWidget`, mismo esqueleto
  que `CashRegisterWorkspace` (sin `KPIBar` — no es uno de los subtemas
  invocados y requeriría datos reales que esta fase no construye).
  **Cada una de las 61 rutas resuelve hoy a un `ViewState.EMPTY` real**
  (nunca a `None`) vía `create_state_widget` — el mismo mecanismo de
  placeholder que `cash_register` ya usa para sus propias secciones sin
  página construida, así que no se inventó un componente "coming soon"
  nuevo. Un `page_factories` opcional permite inyectar páginas reales sin
  tocar este archivo cuando existan.

### Densidad

`frontend/desktop/design_system/` no tiene ningún sistema de perfiles
`compact`/`comfortable`/`touch` implementado en ningún lado — ni siquiera
`cash_register` lo usa; es aspiracional (§90 del prompt, targets táctiles
48-56px nunca materializados). Esta fase no inventó un `DensityProvider`
nuevo unilateralmente para un solo módulo — usó el único lever de densidad
que sí existe de verdad: `PageHeader(compact=...)` (reduce el margen
vertical) más el mismo colapso de ancho de `SideNav` bajo
`ResponsiveBreakpoints.COMPACT` que `cash_register_workspace.py` ya aplica
en su propio `resizeEvent`. Documentado como decisión de alcance explícita,
no como omisión silenciosa.

### Tema

Sin código nuevo: cada componente usado (`PageHeader`, `SideNav`,
`StateWidget`) ya es theme-aware vía el QSS global que aplica
`ThemeManager` — este módulo nunca lee un color ni llama
`setStyleSheet()` (verificado por los guardrails `has_no_hardcoded_colors`/
`has_no_inline_styles`).

## Errores encontrados y corregidos antes de verificar en verde

Tres falsos positivos, misma clase de problema que el guardrail de
Fidelidad ya causó en CRM-13 (un escaneo de texto sin distinguir contexto):

1. **`test_customers_crm_routes_use_stable_dotted_ids`** — el docstring del
   propio `customers_crm_routes.py` citaba literalmente
   `route_id="..."` como ejemplo de sintaxis, y el regex del guardrail lo
   capturó como una ruta real con id `"..."` (fuera del namespace
   `customers.`/`crm.`). Reescrito sin la cita literal.
2. **`test_customers_crm_ui_does_not_receive_app_container`** — el
   docstring de `customers_crm_presenter.py` mencionaba la palabra
   `AppContainer` en prosa (explicando qué NO se recibe) y el regex la
   detectó sin importar el contexto. Reescrito sin el nombre literal.
3. **`test_customers_crm_ui_has_no_raw_sql`** — `self._nav.select(row)`
   (el propio método público de `SideNav`) coincide con `\bSELECT\b`
   (case-insensitive) del escáner de palabras clave SQL. Se reemplazó por
   la misma lógica que `SideNav.select()` ya implementa internamente
   (chequeo de rango + `setCurrentRow()`), evitando la palabra "select" en
   el código fuente. Vale la pena recordar: cualquier módulo CRM futuro que
   llame a `SideNav.select(...)` por su nombre chocará con este mismo
   guardrail — usar `setCurrentRow()` directamente en su lugar.

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py \
  tests/unit/test_customers_crm_ui_workspace.py -q
# 22 guardrails passed (0 skipped — routes_are_stable ya no se salta) + 23 passed
```

- 23 pruebas nuevas (`tests/unit/test_customers_crm_ui_workspace.py`,
  headless vía `QT_QPA_PLATFORM=offscreen`, mismo patrón que
  `test_transfers_ui_workspace.py`): las 61 rutas declaradas usan el
  namespace canónico y son únicas, `visible_routes`/`grouped_routes`
  respetan capacidades por grupo, el workspace construye el stack completo
  con capacidades totales, muestra `NO_PERMISSION` sin ninguna, solo
  construye rutas del grupo permitido con capacidades parciales,
  `select_route`/`refresh_permissions` funcionan, `page_factories`
  reemplaza el placeholder, y el colapso de `SideNav` por breakpoint
  responde a `resize()`.
- Los 22 guardrails de CRM-1 (ahora completos — `routes_are_stable` dejó de
  saltarse) pasan en verde.
- 563 tests combinando guardrails + UI + toda la suite `customers`/`crm`
  (unit + integración) pasan juntos — cero regresión.
- Sintaxis limpia en todo el repositorio.

## Pendiente (próximas fases)

- **Páginas reales** para cada uno de los 61 route_id — CRM-15+, grupo por
  grupo, siguiendo el mismo orden en que sus QueryServices/UseCases ya
  existen (Clientes/Crédito/Segmentación tienen la base más completa desde
  CRM-3/8/10; Cotizaciones queda bloqueada hasta que exista un bounded
  context de Cotizaciones real, CRM-13's hallazgo).
- **Registro en el menú global de la app** (`interfaz/menu_lateral.py`/
  `main_window.py`) — diferido explícitamente; requiere antes decidir si
  coexiste con el botón legacy `"CLIENTES"` o lo reemplaza, y qué código de
  módulo/permiso usar. No es una omisión, es una decisión que esta fase
  identificó pero no le correspondía tomar unilateralmente dado el riesgo
  sobre un archivo compartido por toda la app.
- **`DensityProvider`/perfiles compact-comfortable-touch reales** — sistema
  transversal de `design_system/`, no de este módulo; señalado aquí como
  gap pre-existente confirmado, no introducido por CRM-14.
- **Iconos reales (SVG/icon-font)** — `Icons` sigue siendo un catálogo de
  identificadores sin glifo propio; cuando el design system agregue
  assets reales, este módulo no necesita cambios (ya usa `Icons.CUSTOMERS`
  por identificador, nunca un glifo inline).
