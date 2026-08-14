# CRM-15 — Dashboard: KPIs, gráficas, alertas, actividades, pipeline

Fecha: 2026-08-13. Primer feature page real en
`frontend/desktop/modules/customers_crm/` (CRM-14 solo dejó rutas +
navegación + 61 placeholders). Fuente de diseño:
`docs/refactor/customers_crm_master_prompt.md` §57 (`CustomerDashboardQueryService`,
nombrado y diferido explícitamente desde CRM-12) y §90 ("Dashboard: máx. 6
KPIs principales... La UI no calcula KPIs").

## Los 6 KPIs de §90 y de dónde sale cada uno

| KPI | Fuente | Fase que ya lo construyó |
|---|---|---|
| Leads nuevos | `LeadDirectoryQueryService.count_new()` (nuevo, ver abajo) | CRM-4, extendido aquí |
| Leads por atender | `LeadDirectoryQueryService.list_directory()` filtrado | CRM-4 |
| Oportunidades abiertas | `SalesPipelineForecastQueryService.get_forecast().open_count` (nuevo campo) | CRM-5, extendido aquí |
| Pipeline ponderado | `SalesPipelineForecastQueryService.get_forecast().weighted_pipeline` | CRM-5 |
| Actividades vencidas | `CRMActivityQueryService`/`CRMTaskQueryService`.`list_overdue_for()` | CRM-6 |
| Casos fuera de SLA | `SLAQueryService.list_breached()` | CRM-7 |

`CustomerDashboardQueryService` (`backend/application/crm/queries/
customer_dashboard_query_service.py`) es composición pura sobre las seis —
mismo criterio que `Customer360QueryService` (CRM-12)/`CRMBIExportQueryService`
(CRM-13): ningún número se recalcula con lógica paralela.

## Bug real encontrado por los tests, no un bug de test: "Leads nuevos" no puede ser personal

Primer borrador calculó `leads_new_count` igual que `leads_pending_count` —
filtrando `LeadDirectoryQueryService.list_directory()` (con alcance OWN/TEAM
vía `assigned_user_id`) por `status == NEW`. Un test de integración lo
atrapó de inmediato: un lead en estado NEW **siempre** tiene
`assigned_user_id = None` (`AssignLeadUseCase` es lo único que lo asigna, y
asignar mueve el estado NEW→ASSIGNED en el mismo paso) — así que un lead
NEW nunca puede aparecer en el directorio con alcance de NADIE. El KPI
habría marcado 0 siempre, para cualquier usuario.

Corrección: `LeadDirectoryQueryService.count_new()` (nuevo método,
`backend/application/crm/queries/lead_directory_query_service.py`) —
**la única lectura deliberadamente SIN alcance** en ese servicio, mismo
criterio que `CustomerLookupQueryService` (CRM-12) ya aplicó para su propia
única consulta sin `CustomerDataScopeResolver`: "Leads nuevos" es
inherentemente una cola de triage compartida, no una posesión personal.
Reutiliza `CRMLeadRepository.list_open()` (construido junto con
`list_owned_by()` desde CRM-4, sin consumidor hasta ahora) en vez de
agregar una consulta SQL nueva. Gateado por `CRMPermissions.LEADS_VIEW`
(flat, no la variante `.ver.propia`/`.ver.equipo`).

## Otros dos campos aditivos, no reconstrucciones

- **`SalesPipelineForecast.open_count`** — el conteo de
  `open_opportunities` ya se calculaba dentro de `get_forecast()` y nunca
  se exponía; se agregó como campo aditivo (`len(open_opportunities)`),
  mismo patrón que el `receivable_status` de CRM-13.
- **`get_forecast(as_of=...)`/`list_overdue_for(as_of=...)`/
  `list_breached(as_of=...)`** ya existían con parámetro `as_of` opcional
  desde sus fases originales (CRM-5/6/7) — `CustomerDashboardQueryService.
  get_dashboard()` simplemente los expone con su propio `as_of: str | None`,
  para que las seis secciones compartan el mismo instante "ahora" y para
  que los tests puedan fijar un punto en el tiempo determinista en vez de
  depender de vencimientos hardcodeados en el pasado/futuro real.

## UI: `CustomersCrmOverviewPage` (§90's estructura: KPIs → gráfica → alertas → actividad)

`frontend/desktop/modules/customers_crm/pages/overview_page.py`, cableada
en `customers_crm_workspace.py._create_page()` para la ruta
`customers.overview` (antes un placeholder `ViewState.EMPTY` desde CRM-14).

- **KPIs**: `KPIBar`/`KPIDTO` (ya usado en CRM-14 para gates; primer uso
  real con datos). Actividades vencidas/Casos fuera de SLA usan
  `variant="danger"` cuando el conteo es > 0, `"success"` en caso
  contrario — variante semántica, nunca un color hardcodeado (harían
  fallar `test_customers_crm_ui_has_no_hardcoded_colors`).
- **Gráficas**: `HtmlChartView` + `ChartDataDTO`/`ChartType.BAR` +
  `series_from()` (`backend/application/dto/charts/chart_data.py`,
  `frontend/desktop/components/chart_view.py`) — el mismo mecanismo ECharts
  que §79 nombra, no `ChartDTO`/`ChartBridge` con ese nombre literal (otro
  caso del patrón ya visto en CRM-14 con `ModuleSidebar`/`IconProvider`:
  el master prompt nombra la pieza conceptual, el nombre real de clase es
  otro). Pipeline por etapa, categorías = nombres de etapa resueltos vía
  `CRMUnitOfWork.stage_definitions.list_active_ordered()` (nunca el
  `stage_id` opaco).
  Degrada a la alternativa tabular automáticamente si `QtWebEngine` no
  está disponible (mecanismo ya construido en `HtmlChartView`, sin cambios
  aquí).
- **Alertas**: `AlertCard` (`frontend/desktop/components/cards.py`) +
  un `_AlertsBar` propio que mirror-ea
  `frontend/desktop/modules/purchasing/purchasing_module_shell.py`'s
  `AlertsBar` — un `AlertCard(variant="danger")` por cada KPI en rojo,
  oculto por completo cuando no hay alertas.
- **Actividades**: `StandardTable` listando las actividades/tareas
  vencidas más recientes (`recent_overdue_activities`/
  `recent_overdue_tasks`, tope `recent_limit` — cuenta completa vs. lista
  mostrada son campos separados a propósito, para que el KPI nunca mienta
  aunque la tabla solo muestre las 5 más recientes).
- **Pipeline** (como sección, además del KPI): la misma gráfica de barras
  por etapa sirve como la vista "pipeline" pedida — no se construyó un
  Kanban de oportunidades (eso es `crm.pipeline`, un placeholder aparte,
  fuera de alcance de esta fase — "Dashboard" no es "Pipeline board").

Ciclo de vida `ensure_loaded()`/`reload()` — mismo patrón que
`frontend/desktop/modules/purchasing/pages/procurement_dashboard_page.py`.
`CustomersCrmWorkspace` gana `_ensure_active_page_loaded()`, llamado tras
construir rutas y en cada navegación — la carga perezosa (lazy) de
`CustomersCrmOverviewPage` es el primer caso real que la necesitaba (los
placeholders de CRM-14 no tienen estado que cargar).

`reload()` nunca deja la página en blanco: cualquier excepción (incluyendo
`presenter.dashboard()` sin nada conectado) se atrapa y se muestra como un
estado de error con el mensaje real, igual que
`ProcurementDashboardPage.reload()`.

## `CustomerCrmPresenter.dashboard()` — nuevo método, no una query service cruda

CRM-14 dejó `query_services`/`use_cases` como diccionarios vacíos
("wiring... es trabajo de cada fase futura"). Esta fase agrega
`CustomerCrmPresenter.dashboard()`: busca `query_services["dashboard"]` y
llama `.get_dashboard(actor_user_id=..., team_member_ids=...)` — mismo
patrón "el presenter expone un método de negocio nombrado, no el
QueryService crudo" que `ProcurementDashboardPage` ya usa
(`presenter.analytics_kpis()`). Si nada está conectado (`query_services`
vacío — sigue siendo el caso hoy, ver "Pendiente"), devuelve un
`CustomerDashboardView()` vacío en vez de lanzar, para que la página
siempre tenga algo seguro que renderizar.

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py \
  tests/unit/test_customers_crm_ui_workspace.py \
  tests/unit/test_customers_crm_overview_page.py \
  tests/integration/crm/test_customer_dashboard_query_service.py -q
# 22 guardrails + 23 + 13 + 11 = 69 passed
```

- 27 pruebas nuevas de backend (11 `test_customer_dashboard_query_service.py`
  + 3 `count_new()` en `test_lead_application.py` + el resto son
  aserciones dentro de las anteriores), 13 de UI
  (`test_customers_crm_overview_page.py`) — cubren: KPIs vacíos, conteo de
  leads nuevos sin alcance vs. pendientes con alcance, oportunidades
  abiertas + pipeline ponderado, nombres de etapa en el desglose,
  actividades/tareas vencidas fusionadas sin duplicados entre un equipo,
  casos fuera/dentro de SLA según `as_of`, `recent_limit` no afecta los
  conteos, variantes de KPI danger/success, alertas solo cuando hay algo
  que alertar, gráfica vacía cuando no hay pipeline, `reload()` nunca dejar
  la página en blanco ante un error, y `ensure_loaded()` idempotente.
- Los 22 guardrails de CRM-1 (incluyendo `routes_are_stable`) siguen en
  verde — la primera página real no violó ninguno.
- 790 tests combinando toda la suite `customers`/`crm` (unit+integración) +
  las pruebas de UI de CRM-14/15 pasan juntos — cero regresión, incluyendo
  las 23 pruebas de `test_customers_crm_ui_workspace.py` de CRM-14 (la
  ruta `customers.overview` que antes devolvía un placeholder ahora
  construye una página real, y sus fixtures con presenters falsos sin
  `.dashboard()` real siguen pasando porque `reload()` degrada a un estado
  de error en vez de reventar).
- Sintaxis limpia en todo el repositorio.

## Pendiente (próximas fases)

- **Conectar `query_services["dashboard"]` a una `CustomerDashboardQueryService`
  real con una conexión de base de datos viva** — sigue sin resolverse
  porque depende de la misma decisión que CRM-14 ya dejó pendiente (cómo
  se registra el módulo completo en la app: `interfaz/menu_lateral.py`/
  `main_window.py`, y de ahí cómo obtiene una conexión real). Hasta
  entonces, `CustomersCrmOverviewPage` es real y probada, pero solo
  mostrará el estado de error/vacío en la app corriendo de verdad.
- **Las otras 60 rutas** siguen siendo placeholders — CRM-16+ construye
  páginas reales grupo por grupo (Clientes/Crédito/Segmentación tienen la
  base de backend más completa desde CRM-3/8/10).
- **KPIs secundarios** (§90 menciona "+ secundarios" sin enumerarlos) — no
  se inventaron; el dashboard actual expone exactamente los 6 principales
  más lo que ya cabía naturalmente en la sección de pipeline/actividad.
