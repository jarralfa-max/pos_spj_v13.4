# BI-26 — Forecast UI

Estado: **DONE** (primera página que dispara cómputo real, no solo lectura)

## Alcance

§14/§24-26: página "Forecast" — demanda pronosticada por producto/sucursal,
con exactitud del modelo. Primera página del módulo nuevo que **ejecuta**
una operación (generar un forecast), no solo lee un payload ya calculado.

## Decisión central: componer `DemandPlanningService` real, misma cadena que ya valida BI-12

`DemandPlanningService` (BI-12) es el primer consumidor real de todo el
`ForecastingPlatform` (BI-7..11), ya validado end-to-end contra SQLite real
en `tests/integration/test_demand_planning_service_sqlite.py`. BI-26 no
reimplementa esa orquestación — solo la expone en una UI por primera vez.

**Hallazgo de layering durante esta fase:** el primer borrador del
presenter importaba directamente
`backend.infrastructure.db.repositories.forecasting.*` para componer el
servicio — esto rompe el patrón que todo presenter de BI ha seguido hasta
ahora (`ExecutiveDashboardPresenter`/`AnalyticalSectionPresenter` solo
importan de `backend.application.*`, nunca de `backend.infrastructure.*`,
igual que CLAUDE.md exige — "PyQt no debe... conocer infraestructura
directamente"). Se corrigió extrayendo esa composición a una nueva función
de fábrica en la capa de aplicación,
`backend/application/forecasting/services/demand_planning_factory.py`
(`build_demand_planning_service(connection)`), que el presenter ahora
importa en su lugar. Efecto secundario útil: el guardrail genérico del
módulo (`test_pages_do_not_access_database_or_repositories`, que prohíbe la
subcadena `"repositories"` en cualquier archivo del módulo) dejó de disparar
un falso positivo — no porque se debilitara el guardrail, sino porque la
importación prohibida en efecto no debía vivir ahí.

**Segundo hallazgo:** `BranchQueryService`/`BaseQueryService`
(`backend/application/queries/`) es un scaffold sin ninguna implementación
real de `QueryDataSource` en todo el repo — por defecto usa
`EmptyQueryDataSource()`, así que construirlo con una conexión SQLite cruda
(`BranchQueryService(connection)`) habría producido una caja de búsqueda de
sucursales silenciosamente vacía siempre, sin ningún error visible. Se
evitó usando `BiDashboardQueryService.filter_options()["branches"]` (BI-4)
en su lugar — el mismo catálogo real que ya alimenta el filtro global de
sucursal del dashboard ejecutivo.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/application/forecasting/services/demand_planning_factory.py` | `build_demand_planning_service(connection)` — única función de composición real para `DemandPlanningService` desde una conexión cruda; usada aquí y disponible para cualquier futuro caller (API, otra UI). |
| `frontend/desktop/modules/business_intelligence/presenters/forecast_explorer_presenter.py` | `ForecastExplorerPresenter` — `search_products`/`search_branches` (autocomplete, §20) + `forecast(product_id, branch_id, horizon_days)` que llama `DemandPlanningService.forecast_product_demand()` real y traduce `ForecastRun`/`ForecastResult` a `KPIDTO`s + un `ChartDataDTO` de 3 series (pronóstico/límite inferior/límite superior). Errores reales del dominio (ej. `MetricInputError` cuando WAPE es indefinido por cero ventas) se traducen a `ForecastUnavailableError`, nunca un stack trace. |
| `frontend/desktop/modules/business_intelligence/pages/forecast_explorer_page.py` | `ForecastExplorerPage` — `ProductSearchBox`+`BranchSearchBox` (§20) + `IntegerInput` de horizonte (arranca en 0, §22; su valor por defecto viene de `BiSettingsService.forecast_window_days`, §23) + botón "Generar forecast" (acción explícita, no auto-genera al cargar la página) + `KPIBar` + 1 `HtmlChartView`. |
| `business_intelligence_routes.py` (editado) | `bi_forecast` ahora construye `ForecastExplorerPage` cuando hay `connection`. |

## Por qué el botón no se dispara automáticamente al entrar a la página

A diferencia de las páginas de solo lectura (BI-24/25), esta página no tiene
nada que mostrar hasta que el usuario elige un producto — `ensure_loaded()`
solo rellena el horizonte por defecto, nunca llama `refresh()`
automáticamente (evita un `QMessageBox` sorpresa al navegar a la página).

## Auditoría REGLA CERO

Sin identidad nueva — solo composición/traducción; `ForecastRun`/
`ForecastResult` (BI-7) ya validan UUIDv7 en su propio `__post_init__`. N/A.

## Tests

`test_forecast_explorer_presenter.py` (9: mapeo KPI/chart puro, degradación
sin filas de productos/sucursales, validación de `product_id`/
`horizon_days`, un caso real de cero-ventas que confirma el error de WAPE se
traduce correctamente, y un caso con 120 días de historia real sembrada que
confirma el forecast estabiliza en el valor constante esperado),
`test_forecast_explorer_page.py` (4: construcción, horizonte por defecto,
selección de producto/sucursal, ruteo). **13 tests nuevos, todos verdes**
(66 en el paquete `business_intelligence` completo).

## Pendiente

- Sin persistencia de "forecast favoritos"/comparación entre runs — cada
  clic genera un run nuevo (comportamiento correcto per §69, "nunca
  sobrescribir", pero no hay UI para navegar el historial de runs todavía).
- Sin selector de familia de modelo — usa siempre `model_key
  ="demand_planning_default"` (el mismo default que `DemandPlanningService`
  ya documenta como bootstrap sin gate de aprobación humana).
- BI-27 construye Decision Intelligence/Recomendaciones; BI-28 Alertas.
