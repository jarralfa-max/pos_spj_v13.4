# BI-0 — Auditoría de legacy: Business Intelligence / Analytics / Forecasting / Decision Intelligence

Estado: **DONE** (auditoría). BI-1..BI-32 también **DONE** — ver
`BI-1_guardrails.md` .. `BI-32_legacy_removal.md`. BI-33 (validación final)
es la última fase del roadmap. Ningún archivo legacy fue eliminado en ninguna pasada;
BI-4 sí **relocalizó** (no eliminó) los 10 archivos `MOVE`-clasificados del
dashboard BI a `backend/application/analytics/`, actualizando sus 11 sitios
de import. El resto de las pasadas fue código nuevo aditivo: permisos,
eventos, semantic layer, snapshots/cache, plataforma de forecasting completa
BI-7..BI-12 con persistencia SQLite real (migración 254), 4 servicios de
recomendación (BI-13 Inventory Forecast, BI-14 Purchase Planning — corrige
la violación TreasuryService de BI-0 vía `FinanceQueryPort` —, BI-15
Production Planning, BI-16 Pricing Intelligence, BI-17 Branch Intelligence),
3 bounded contexts que cierran el arco de "Decision Intelligence" (BI-18
`decision_intelligence` unifica los 5 tipos de recomendación bajo
`BusinessRecommendation` + ciclo de vida de aprobación; BI-19
`scenario_planning` reutiliza los mismos servicios deterministas con inputs
perturbados para what-if de precio/demanda; BI-20 `analytical_alerting`
motor de alertas genérico por umbrales con dedup/cooldown/ciclo de vida), y
el cierre del arco de integración externa (BI-21 conecta el Alert Engine a
la Notification Management real vía puertos, sin llamar WhatsApp directo;
BI-22 expone 4 endpoints GET reales en la app FastAPI ya existente del
repo, respaldados por persistencia SQLite genuina de BI-11; BI-23/24
construyen el primer módulo desktop nuevo —
`frontend/desktop/modules/business_intelligence/` — con navegación completa
y una página ejecutiva real conectada al `BiDashboardService` ya limpio que
BI-0 encontró, deliberadamente NO wireada todavía en `main_window.py` para
no producir una regresión visible frente al dashboard legacy de 10
secciones). Suite acumulada de tests nuevos: **497/497 verdes** (BI-1..BI-24),
cero regresiones, cero errores de sintaxis en todo el repo.

## Alcance

Auditoría previa a la creación del bounded context canónico de **Business
Intelligence, Operational/Management Analytics, Forecasting, Decision
Intelligence, Scenario Planning y Alerting** hacia
`backend/{domain,application,infrastructure}/{analytics,forecasting,decision_intelligence,scenario_planning}`
+ `frontend/desktop/modules/business_intelligence/`, siguiendo el mismo patrón
ya aplicado a Inventario, Cash Register, CRM, Mermas/Losses, Procesamiento
Cárnico, Procurement, Assets, Loyalty y Orders/Delivery.

Este documento **no elimina ni modifica ningún archivo legacy**. Solo
clasifica.

## Hallazgo principal

El BI *dashboard ejecutivo* actual (`modulos/reportes_bi_v2.py` +
`BiDashboardService` + `Bi*QueryService`) es, sorprendentemente, **ya limpio**:
cero SQL en UI, sin `modulos.design_tokens`/`ui_components`/`spj_styles`
mezclados con lógica de negocio, arquitectura UI→Service→QueryService→DB ya
documentada en `docs/architecture/BI_DASHBOARD.md`. El problema real no está
en el dashboard, está en el **Forecasting / Decision Intelligence**: existen
**5 implementaciones de forecast independientes**, al menos **3 activas en
producción simultáneamente**, más 2 "god objects" (`CEODashboard`,
`DecisionEngine`) que llaman directo a `TreasuryService`, y un motor completo
(`ReplenishmentEngine`, el más production-shaped de todos, con run-logging y
eventos) que está **muerto — nunca wireado en `app_container.py`**.

## Inventario de legacy detectado

| Archivo | Líneas | Clasificación | Nota / condición de eliminación |
|---|---|---|---|
| `modulos/reportes_bi_v2.py` | 1331 | `REUSE` (base de migración UI) | Ya es "clean UI" (cero SQL, todo vía `BiDashboardService`). Usa legacy `modulos.design_tokens`/`ui_components`/`spj_styles` y `QTableWidget`/`QTabWidget`/`QGroupBox`/`setStyleSheet` — violación de reglas §89/§90 del prompt maestro, pero de **presentación**, no de lógica. Condición de eliminación: reemplazado por `frontend/desktop/modules/business_intelligence/` (BI-23..BI-25) con Design System + `ModuleSidebar` + `StandardTable V2`, delegando a los mismos/mejorados Application Services. |
| `modulos/bi_dashboard_view.py`, `modulos/bi_charts.py`, `modulos/bi_theme.py` | 279+231+78 | `REUSE` | Renderer HTML/SVG offline sin CDN, ya theme-aware vía `design_tokens`. Puede portarse casi 1:1 a `ChartCard`/`HtmlChartView` (§93) del nuevo módulo. |
| `backend/application/dto/bi_dashboard_dto.py` | 219 | `MOVE` + dedupe | Define `ChartData` propio, **duplicado** del `ChartDataDTO`/`ChartSeriesDTO` canónico ya adoptado por Losses/Orders-Delivery/Procurement/Inventory (`backend/application/dto/charts/chart_data.py`). Condición: migrar a `ChartDataDTO` como parte de BI-3 (Semantic Layer) y mover el resto (`DashboardFilters`, `KpiCard`, `HighlightCard`, `Alert`, `Insight`, `Prediction`, `DashboardPayload`) a `backend/application/analytics/dto/`. |
| `backend/application/services/bi_dashboard_service.py` | 459 | `MOVE` | Orquestador limpio (permisos, cache TTL, período-sobre-período). Se relocaliza a `backend/application/analytics/services/` sin reescritura mayor. |
| `backend/application/queries/bi_dashboard_query_service.py` | 87 | `MOVE` (con fix) | Compone los 5 query services de abajo. Contiene 3 SQL crudos propios en `filter_options()` — extraer a repository. Se relocaliza a `backend/application/analytics/queries/`. |
| `backend/application/queries/bi_sales_query_service.py` | 179 | `MOVE` | SQL de ventas/COGS/margen/top-productos. Candidato a `SalesAnalyticsQueryService` (§10). |
| `backend/application/queries/bi_inventory_query_service.py` | 117 | `MOVE` | Candidato a `InventoryAnalyticsQueryService` (§10) — verificar solapamiento con `backend/application/inventory/analytics/inventory_analytics_service.py` (ya existente, más moderno) antes de duplicar. |
| `backend/application/queries/bi_finance_query_service.py` | 70 | `MOVE` | Candidato a `FinanceAnalyticsQueryService` (§10). |
| `backend/application/queries/bi_cash_query_service.py` | 74 | `MOVE` | Sub-fuente de Finance Analytics. |
| `backend/application/queries/bi_forecast_query_service.py` | 56 | `REPLACE` | Forecast por media móvil simple, "no ML". Es el único forecast alcanzable desde el dashboard hoy. Reemplazar por `ForecastingPlatform` (BI-6..BI-11) manteniendo el mismo contrato de salida (`forecast_series`) hasta el corte. |
| `backend/application/queries/business_intelligence_query_service.py` | 18 | `DELETE` (candidato, verificar consumidores) | Scaffold genérico de búsqueda/KPI-index, no referenciado por `reportes_bi_v2.py`. Confirmar cero-consumidores antes de retirar. |
| `backend/application/services/bi_export_service.py` | 179 | `REUSE` | Export xlsx/pdf/csv desde `DashboardPayload` ya calculado, sin acceso a DB. Se relocaliza a `backend/infrastructure/analytics/exports/`. |
| `backend/application/services/bi_settings_service.py` | 62 | `MOVE` | Thresholds configurables (merma%, margen bajo%, etc.) — base de `AnalyticalAlertRule`/§48 configuración. Se relocaliza a `backend/application/analytics/services/`. |
| `core/services/analytics/analytics_engine.py` | ~700 | `BLOCKED` | **Activo en producción** (`app_container.py:723-725`, suscrito a `SALE_CREATED`/`PRODUCTION_EXECUTED`, prioridad 5). Escribe `bi_sales_daily`/`bi_transformations` vía SQL crudo (UPSERT). Condición de eliminación: reemplazado por `AnalyticalSnapshotWorker` (§65/§125) consumiendo los mismos eventos hacia el esquema de snapshots canónico (BI-5). |
| `core/services/forecast_engine.py` | 103 | `BLOCKED` | SES (α=0.3). Solo invocado desde `core/services/scheduler_service.py`, no vía `app_container`. Condición de eliminación: cubierto por modelo `SES` del Model Registry (BI-9). |
| `core/services/forecast_service.py` | 149 | `DELETE` (candidato) | Holt-Winters (statsmodels). **Huérfano de producción** — solo referenciado en tests. Publica `FORECAST_GENERADO`. Condición: confirmar cero-consumidores reales y retirar directamente en BI-32 tras portar su lógica (Holt-Winters ya es uno de los modelos baseline del prompt, §19) al Model Registry. |
| `core/services/actionable_forecast.py` | 316 | `BLOCKED` | **Activo** (`app_container.py:515-518`, consumido por `CEODashboard`). Llama directo a `treasury_service.estado_cuenta()` — viola §10 (BI no debe depender directo de TreasuryService). Envuelve `DemandForecastEngine`. Condición de eliminación: reemplazado por `PurchaseRecommendation`/`ProductionRecommendation` (BI-14/BI-15) consumiendo `FinanceAnalyticsQueryService` (puerto, no `TreasuryService` directo) para `capital_required` (§75). |
| `core/forecast/demand_forecast_engine.py` | 397 | `BLOCKED` | 4 métodos (moving_avg_7/30, weighted_avg, exp_smoothing) + estacionalidad + MAE/RMSE/MAPE — el más "completo" en features de backtesting parcial. Buen punto de partida para `ForecastEvaluator`/modelos baseline (BI-9/BI-10). Condición: reemplazado cuando `ForecastModelRegistry` cubra paridad de métodos + backtesting formal (WAPE/BIAS que hoy no tiene). |
| `core/forecast/seasonality_detector.py` | 95 | `REUSE` (portar lógica) | Puro (`@staticmethod`, sin DB). Factor de estacionalidad semanal — portar como feature de `TimeSeriesDatasetBuilder` (BI-8). |
| `core/forecast/replenishment_engine.py` | 502 | `BLOCKED` — **código muerto, no eliminar aún** | **Nunca wireado en `app_container.py`.** Es el motor más "production-shaped": corre `DemandForecastEngine` + `SafetyStockCalculator`, decide COMPRA/PRODUCCION/TRANSFERENCIA, loguea `forecast_run_log`. Publica evento string crudo `"FORECAST_GENERATED"` (inglés, no registrado, distinto del `FORECAST_GENERADO` canónico). Es la **referencia funcional más cercana** a `PurchaseRecommendation`+`ForecastRun` del prompt maestro (§24/§29/§71). Condición: su lógica se re-implementa dentro de `ForecastingPlatform`/`ReplenishmentEngine` canónico (BI-11/BI-13/BI-71); no se elimina hasta que exista el reemplazo con tests, aunque hoy no tenga consumidores en producción. |
| `core/forecast/safety_stock_calculator.py` | 120 | `REUSE` (portar lógica) | Puro, fórmula clásica `Z·σ·√(lead_time)` + niveles de servicio 90-99.9%. Portar directo a `SafetyStockPolicy` (§72), ya soporta el patrón "métodos configurables" que pide el prompt (agregar `FIXED_DAYS`/`DEMAND_VARIABILITY`/`CUSTOM` junto al existente `SERVICE_LEVEL`). |
| `core/services/enterprise/demand_forecasting.py` | 479 | `BLOCKED` | **Activo** (`app_container.py:690`, usado también por `report_engine_v2.py`). WMA_7/SMA_14/SMA_30 + clasificación de tendencia. Tercer motor de forecast simultáneo en producción. Condición de eliminación: mismo destino que `demand_forecast_engine.py` — absorbido por Model Registry (BI-9). |
| `core/services/ceo_dashboard.py` | 236 | `BLOCKED` | God-object que agrega Treasury + AlertEngine + DecisionEngine + ActionableForecast + FinancialSimulator + AIAdvisor + Loyalty — **fuera del alcance de BI puro** (mezcla ejecución/dominio financiero con analítica). Se mantiene operando; su reemplazo (`ExecutiveDashboardDTO`, BI-24) solo cubre la porción analítica/BI, no las llamadas directas a Treasury. Documentar explícitamente en BI-24 qué queda fuera. |
| `core/services/decision_engine.py` | 580 | `BLOCKED` | "Suggestion-only" — ya respeta el principio §36/§39 de no auto-ejecutar, pero llama `treasury_service.kpis_financieros()` directo (misma violación que `actionable_forecast.py`). Es el precedente más cercano a `DecisionIntelligenceEngine`/`BusinessRecommendation` (§36/§37). Condición de eliminación: absorbido por `DecisionIntelligenceEngine` (BI-18) mediando el acceso a Finance vía `FinanceAnalyticsQueryService`. |
| `core/services/alert_engine.py` | 562 | `BLOCKED` | Alertas con severidad (low/medium/high/critical) cross-dominio. Precedente de `AnalyticalAlertRule`/`AnalyticalAlert` (§46/§47/§48), pero sin dedupe/cooldown/lifecycle formal (§49/§50) ni integración con Notification Management (§51). Condición de eliminación: absorbido por `Alert Engine` canónico (BI-20/BI-21). |
| `core/services/bi_service.py` | 33 | `DELETE` (ya deprecado) | `app_container.py` ya lo desactivó (`self.bi_service = None`, comentario "BI unificado"). Solo referenciado por `tests/test_fase2_bi_cajeros.py`. Eliminar junto con migrar ese test a `Bi*QueryService` en BI-32. |
| `repositories/bi_repository.py` | 101 | `DELETE` (ya deprecado) | Mismo estado que `bi_service.py` — import ya comentado en `app_container.py`. |
| `webapp/api_dashboard.py` | 487 | `BLOCKED` | **15 SELECT crudos** directo en endpoints Flask — tercera implementación paralela de "dashboard" (junto a `ui/dashboard.py` operacional y `reportes_bi_v2.py` ejecutivo). Fuera del alcance inmediato (no es PyQt), pero candidato natural para consumir `backend/api/analytics/` (§57/BI-22) cuando exista. No tocar en esta fase. |
| `ui/dashboard.py` | 1477 | `OUT_OF_SCOPE` | Dashboard operacional POS en tiempo real (ventas de hoy, cola WhatsApp) — no es el dashboard ejecutivo/BI. Se documenta para no confundir superficies, no se toca. |

Ningún archivo se clasifica `DELETE` inmediato salvo los ya explícitamente
deprecados (`bi_service.py`, `bi_repository.py`, verificar consumidores). El
resto requiere que exista la ruta canónica de reemplazo antes de retirarse
(regla §150 del prompt maestro: "No eliminar funcionalidad antes de
inventariarla").

## Matriz de paridad de forecast (resumen — detalle en BI-6)

| Implementación | Algoritmo | Wireada en `app_container`? | Toca Treasury directo | Destino canónico |
|---|---|---|---|---|
| `AnalyticsEngine` | N/A (agregador, no forecast) | Sí | No | `AnalyticalSnapshotWorker` |
| `ForecastEngine` (SES) | SES α=0.3 | No (solo scheduler) | No | Modelo `SES` en Model Registry |
| `ForecastService` (Holt-Winters) | Holt-Winters | **No — huérfano** | No | Modelo `HOLT_WINTERS` en Model Registry |
| `ActionableForecastService` | envuelve `DemandForecastEngine` | Sí | **Sí — directo** | `PurchaseRecommendation`/`ProductionRecommendation` |
| `DemandForecastEngine` (core/forecast) | MA7/MA30/WMA/ExpSmoothing + estacionalidad + MAE/RMSE/MAPE | Solo vía `ActionableForecastService` | No | Baseline models + `ForecastEvaluator` |
| `ReplenishmentEngine` | orquesta `DemandForecastEngine`+`SafetyStockCalculator` | **No — código muerto** | No | `ForecastingPlatform` completo (referencia principal) |
| `DemandForecastingEngine` (enterprise) | WMA_7/SMA_14/SMA_30 + tendencia | Sí (`container.forecast_engine`) | No | Modelos baseline en Model Registry |
| `BiForecastQueryService` | media móvil simple | Sí (único alcanzable desde dashboard) | No | Reemplazado manteniendo contrato hasta el corte |

**Conclusión**: 3 motores activos simultáneos en `app_container.py`
(`AnalyticsEngine`, `ActionableForecastService`→`DemandForecastEngine`,
`DemandForecastingEngine`), 1 huérfano (`ForecastService`), 1 muerto pero más
completo (`ReplenishmentEngine`). Ninguno tiene backtesting formal (WAPE/BIAS),
versionado de modelos, ni intervalos de confianza — brecha total contra
§19-§25 del prompt maestro.

## Brechas encontradas (no corregidas en esta pasada)

1. **Duplicación de tablas de snapshot diario**: `ventas_diarias`/`inventario_diario`
   (migración 032) vs `bi_sales_daily`/`bi_product_profit` (migración 062) —
   dos familias paralelas de agregados diarios por sucursal. Reconciliar en BI-5.
2. **Evento no registrado**: `core/forecast/replenishment_engine.py:139` publica
   `"FORECAST_GENERATED"` (string crudo, inglés) en vez del `FORECAST_GENERADO`
   canónico (`core/events/domain_events.py:159`). No hay eventos `ANALYTICS_*`,
   `BI_*` ni `RECOMMENDATION_*` registrados — crear en BI-2/domain events.
3. **Sin permisos granulares**: `CANONICAL_MODULE_PERMISSIONS["INTELIGENCIA_BI"]`
   es una lista plana de 11 códigos (`ver`, `ver_ventas`, …), sin el patrón
   punteado `MODULO.accion` que usan Products/Procurement/Meat Processing. No
   existe `backend/application/*/permissions.py` para BI. Corregir en BI-2,
   siguiendo el estándar de Compras (confirmado como preferencia del usuario,
   ver `[[feedback_permissions_compras_standard]]`).
4. **Cero separación de límites documentada salvo un caso**: solo
   `backend/application/crm/queries/sales_pipeline_forecast_query_service.py`
   documenta explícitamente el límite "CRM calcula forecast operativo; BI hace
   modelos analíticos avanzados; no mezclar con forecast de abastecimiento."
   Ese límite debe respetarse: la `ForecastingPlatform` de BI **no** debe
   absorber el forecast de pipeline comercial de CRM.
5. **`backend/application/inventory/analytics/inventory_analytics_service.py`**
   ya existe y se solapa parcialmente con `bi_inventory_query_service.py`. No
   asumir que BI debe reimplementar — evaluar reuso/composición en BI-4.
6. **Triada domain/application/infrastructure de referencia**: el mejor
   ejemplo existente de la capa objetivo (domain puro + application delgado +
   infra con SQL portable) es Losses: `backend/domain/losses/analytics.py`
   (17 líneas, matemática pura) + `backend/application/losses/analytics.py`
   (34 líneas) + `backend/infrastructure/persistence/loss_analytics_repository.py`
   (19 líneas). Usar como plantilla de tamaño/separación para BI-3/BI-4, no el
   patrón más pesado de `bi_dashboard_service.py` (459 líneas, aceptable porque
   orquesta 5 sub-servicios, no por ser el tamaño objetivo de cada pieza).

## Roadmap BI-0..BI-33

| Fase | Descripción | Estado |
|---|---|---|
| BI-0 | Auditoría de legacy | **DONE** (este documento) |
| BI-1 | Guardrails (tests de arquitectura anti-duplicación) | **DONE** (ver `BI-1_guardrails.md`) |
| BI-2 | Seguridad (permisos granulares, eventos canónicos) | **DONE** (ver `BI-2_security.md`; scopes en runtime quedan pendientes para BI-4+) |
| BI-3 | Semantic Metrics Layer (MetricDefinition, dimensiones, lineage) | **DONE** (ver `BI-3_semantic_layer.md`; sin consumidores reales todavía, eso es BI-4) |
| BI-4 | Consolidación de Query Layer (Analytics QueryServices) | **DONE** (ver `BI-4_query_layer.md`; wiring al MetricRegistry pendiente) |
| BI-5 | Snapshots / Cache (reconciliar `bi_sales_daily` vs `ventas_diarias`) | **DONE** (ver `BI-5_snapshots_cache.md`; decisión: no tocar tablas legacy todavía) |
| BI-6 | Inventario detallado de forecast (matriz de paridad completa) | **DONE** (ver `BI-6_forecast_inventory.md`) |
| BI-7 | Forecast Domain (ForecastingPlatform base) | **DONE** (ver `BI-7_forecast_domain.md`) |
| BI-8 | Time Series Data (datasets, series, dimensiones) | **DONE** (ver `BI-8_time_series_data.md`) |
| BI-9 | Baseline Models (naive, seasonal naive, MA, SES, Holt, Holt-Winters) | **DONE** (ver `BI-9_baseline_models.md`) |
| BI-10 | Backtesting (MAE/RMSE/MAPE/WAPE/MASE/BIAS + selección) | **DONE** (ver `BI-10_backtesting.md`) |
| BI-11 | Forecast Runs (persistencia/versionado, ForecastResult) | **DONE** (ver `BI-11_forecast_runs.md`) |
| BI-12 | Demand Planning (producto/categoría/sucursal) | **DONE** (ver `BI-12_demand_planning.md`; producto+sucursal — categoría/canal pendientes de serie real) |
| BI-13 | Inventory Forecast (cobertura, safety stock, risk) | **DONE** (ver `BI-13_inventory_forecast.md`) |
| BI-14 | Purchase Planning (PurchaseRecommendation) | **DONE** (ver `BI-14_purchase_planning.md`; corrige la violación TreasuryService de BI-0 vía `FinanceQueryPort`) |
| BI-15 | Production Planning (ProductionRecommendation) | **DONE** (ver `BI-15_production_planning.md`) |
| BI-16 | Pricing Intelligence (elasticidad, PriceRecommendation) | **DONE** (ver `BI-16_pricing_intelligence.md`) |
| BI-17 | Branch Intelligence (BranchRecommendation) | **DONE** (ver `BI-17_branch_intelligence.md`) |
| BI-18 | Decision Intelligence Engine (BusinessRecommendation) | **DONE** (ver `BI-18_decision_intelligence.md`) |
| BI-19 | Scenario Planning (What-if) | **DONE** (ver `BI-19_scenario_planning.md`) |
| BI-20 | Alert Engine (lifecycle, dedupe, cooldown) | **DONE** (ver `BI-20_alert_engine.md`) |
| BI-21 | Notification Integration (ERP + WhatsApp vía Notification Management) | **DONE** (ver `BI-21_notification_integration.md`) |
| BI-22 | API Contracts futuros (`backend/api/`) | **DONE** (ver `BI-22_api_contracts.md`) |
| BI-23 | UI Foundations (routes, sidebar, Design System) | **DONE** (ver `BI-23_ui_foundations.md`; no wireado en main_window.py todavía) |
| BI-24 | Executive Dashboard | **DONE** (ver `BI-24_executive_dashboard.md`) |
| BI-25 | Analytical Pages (ventas/inventario/compras/finanzas reales vía `BiDashboardService.section_data()`; producción/precios/sucursales documentados como gap) | **DONE** |
| BI-26 | Forecast UI (product/branch search + `DemandPlanningService` real) | **DONE** |
| BI-27 | Recommendations UI (Decision Intelligence — solo precios, vía `PricingIntelligenceService` real) | **DONE** |
| BI-28 | Alerts UI (2/16 tipos, vía `AnalyticalAlertEngine` real contra KPIs del dashboard) | **DONE** |
| BI-29 | Scenarios UI (price what-if vía `PricingWhatIfService` real) | **DONE** |
| BI-30 | Reports (exportaciones reales vía `BiExportService`; programados documentado como brecha honesta) | **DONE** |
| BI-31 | Responsive / Touch / Accessibility (auditoría + accessible name/description en 7 páginas + 2 combos táctiles) | **DONE** |
| BI-32 | Legacy Removal (2/4 candidatos eliminados con evidencia fresca; 2 corrigen la clasificación original de BI-0) | **DONE** |
| BI-33 | Validación final (checklist del skill de refactor) | **DONE** |

## Documentos de referencia ya existentes (leer antes de BI-3/BI-4)

- `docs/architecture/BI_DASHBOARD.md` — documenta ya casi toda la arquitectura
  actual del dashboard de ventas/finanzas (KPIs, filtros, cache, permisos,
  drill-down pendiente). No reinventar, extender.
- `backend/application/dto/charts/chart_data.py` — contrato de chart canónico
  (`ChartDataDTO`/`ChartSeriesDTO`/`ChartType`/`FreshnessState`) ya adoptado
  por 4 bounded contexts. BI debe consumirlo, no crear uno nuevo.
- `backend/application/products/permissions.py` — plantilla de
  `class <Context>Permissions` a replicar para `AnalyticsPermissions`/
  `ForecastingPermissions`/`DecisionIntelligencePermissions`.
